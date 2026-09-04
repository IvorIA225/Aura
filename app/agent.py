"""
Agent — Cerveau du WhatsApp Agentic Support Bot.

Couche 2 du Framework WAT : orchestre le pipeline complet de traitement
d'un message client :

    1. Détection de langue
    2. Chargement du contexte (historique + knowledge base)
    3. Génération de réponse (LLM principal via LiteLLM)
    4. Auto-Vérification / Self-Check (LLM rapide)
    5. Envoi ou Escalade
    6. Logging & Feedback Loop

Principes :
- L'agent ne connaît PAS l'API WhatsApp → il délègue aux Tools.
- Les règles métier viennent des Workflows (fichiers .md).
- Les connaissances factuelles viennent de knowledge.md.
"""

import logging
from pathlib import Path

import litellm
from langdetect import detect as detect_language_raw

from app.config import get_settings
from app.models import (
    IncomingMessage,
    AgentResponse,
    ConversationContext,
    EscalationTicket,
    SelfCheckResult,
)
from tools.whatsapp import send_text_message
from tools.supabase_db import (
    get_or_create_conversation,
    save_message,
    get_conversation_history,
    log_agent_action,
    log_unanswered_question,
    update_conversation_status,
)
from tools.notion_escalation import create_escalation_ticket

logger = logging.getLogger(__name__)

# ── Constantes ──
MAX_SELF_CHECK_RETRIES = 2


# ══════════════════════════════════════════════════
# Point d'entrée principal
# ══════════════════════════════════════════════════

async def process_message(incoming: IncomingMessage) -> None:
    """
    Pipeline WAT complet pour traiter un message client.

    C'est la fonction appelée par main.py à chaque message reçu.
    """
    settings = get_settings()

    # ── Étape 1 : Détection de langue ──
    language = _detect_language(incoming.text)
    logger.info(f"🌍 Langue détectée: {language}")

    # ── Étape 2 : Chargement du contexte ──
    conversation = await get_or_create_conversation(
        phone=incoming.phone,
        name=incoming.name,
        language=language,
    )
    conversation_id = conversation["id"]

    # Sauvegarder le message entrant
    await save_message(
        conversation_id=conversation_id,
        role="user",
        content=incoming.text,
    )

    # Charger l'historique
    history = await get_conversation_history(incoming.phone)

    # Construire le contexte
    context = ConversationContext(
        client_phone=incoming.phone,
        client_name=incoming.name,
        client_language=language,
        conversation_id=conversation_id,
        history=history,
        current_message=incoming.text,
    )

    await log_agent_action(
        conversation_id=conversation_id,
        action="language_detected",
        details={"language": language},
    )

    # ── Étapes 3-5 : Génération + Self-Check + Retry Loop ──
    agent_response = await _generate_with_self_check(context, settings)

    # ── Étape 6 : Envoi ou Escalade ──
    if agent_response.should_escalate:
        await _handle_escalation(context, agent_response)
    else:
        # Envoyer la réponse au client
        sent = await send_text_message(incoming.phone, agent_response.text)

        if sent:
            await log_agent_action(
                conversation_id=conversation_id,
                action="response_sent",
                details={
                    "model": agent_response.model_used,
                    "tokens": agent_response.tokens_used,
                    "self_check": agent_response.self_check_result.value,
                },
            )
        else:
            await log_agent_action(
                conversation_id=conversation_id,
                action="send_failed",
                status="error",
            )

    # Sauvegarder la réponse de l'agent
    await save_message(
        conversation_id=conversation_id,
        role="assistant",
        content=agent_response.text,
        model_used=agent_response.model_used,
        tokens_used=agent_response.tokens_used,
        self_check_result=agent_response.self_check_result.value,
        self_check_notes=agent_response.self_check_notes,
    )

    # ── Feedback Loop : Détection automatique des questions sans réponse ──
    unanswered_cues = [
        "ne trouve pas d'information",
        "base de connaissances",
        "pas d'information",
        "transmettre votre demande",
        "équipe spécialisée",
    ]
    if any(cue in agent_response.text.lower() for cue in unanswered_cues):
        await log_unanswered_question(
            question=incoming.text,
            client_phone=incoming.phone,
            conversation_id=conversation_id,
            context=agent_response.text,
        )


# ══════════════════════════════════════════════════
# Détection de langue
# ══════════════════════════════════════════════════

def _detect_language(text: str) -> str:
    """
    Détecte la langue du texte du client.
    Retourne un code ISO 639-1 (fr, en, es, etc.).
    Fallback sur 'fr' si la détection échoue.
    """
    try:
        lang = detect_language_raw(text)
        return lang
    except Exception:
        logger.warning("⚠️ Détection de langue échouée, fallback sur 'fr'")
        return "fr"


# ══════════════════════════════════════════════════
# Chargement des fichiers de contexte
# ══════════════════════════════════════════════════

def _load_knowledge_base() -> str:
    """Charge le contenu de knowledge.md."""
    settings = get_settings()
    path = Path(settings.knowledge_path)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.error(f"❌ knowledge.md introuvable: {path}")
        return "(Base de connaissances non disponible)"


def _load_workflow(name: str) -> str:
    """Charge un fichier workflow depuis le dossier workflows/."""
    settings = get_settings()
    path = Path(settings.workflows_dir) / name
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(f"⚠️ Workflow introuvable: {path}")
        return ""


# ══════════════════════════════════════════════════
# Construction des prompts
# ══════════════════════════════════════════════════

def _build_system_prompt(context: ConversationContext) -> str:
    """
    Construit le system prompt pour l'agent à partir des workflows et
    de la knowledge base.

    Architecture WAT : le prompt est assemblé dynamiquement à partir
    des fichiers, pas codé en dur.
    """
    knowledge = _load_knowledge_base()
    workflow = _load_workflow("whatsapp_support.md")
    escalation_rules = _load_workflow("escalation.md")

    return f"""Tu es un agent de support client sur WhatsApp. Tu dois répondre de manière empathique, 
professionnelle et factuelle.

## RÈGLES ABSOLUES
1. Tu réponds UNIQUEMENT avec les informations contenues dans la BASE DE CONNAISSANCES ci-dessous.
2. Tu ne dois JAMAIS inventer d'information (prix, délai, politique, etc.).
3. Si tu ne trouves pas la réponse dans la base de connaissances → dis-le honnêtement et propose d'escalader.
4. Tu réponds dans la langue du client (détectée : {context.client_language}).
5. Tu utilises le prénom du client quand disponible : {context.client_name}.
6. Tes messages sont courts et adaptés à WhatsApp (pas de pavés).
7. Tu utilises 1-2 émojis max par message, avec parcimonie.

## WORKFLOW DE SUPPORT
{workflow}

## RÈGLES D'ESCALADE
{escalation_rules}

## BASE DE CONNAISSANCES
{knowledge}

## CONTEXTE CLIENT
- Nom : {context.client_name}
- Téléphone : {context.client_phone}
- Langue : {context.client_language}
"""


def _build_self_check_prompt(
    original_message: str,
    agent_reply: str,
    client_language: str,
) -> str:
    """
    Construit le prompt pour le Self-Check (modèle rapide).
    Évalue la réponse de l'agent selon la grille de self_check.md.
    """
    knowledge = _load_knowledge_base()
    self_check_workflow = _load_workflow("self_check.md")

    return f"""Tu es un évaluateur de qualité pour un bot de support client WhatsApp.
Tu dois évaluer la RÉPONSE de l'agent selon 5 critères stricts.

## GRILLE D'ÉVALUATION
{self_check_workflow}

## BASE DE CONNAISSANCES (source de vérité)
{knowledge}

## MESSAGE DU CLIENT
{original_message}

## RÉPONSE DE L'AGENT À ÉVALUER
{agent_reply}

## LANGUE ATTENDUE
{client_language}

## FORMAT DE RÉPONSE (JSON strict)
Réponds UNIQUEMENT avec ce JSON, rien d'autre :
{{
    "result": "passed" | "failed_hallucination" | "failed_tone" | "failed_language" | "failed_out_of_scope" | "needs_escalation",
    "notes": "Explication courte du résultat",
    "should_escalate": true | false
}}
"""


# ══════════════════════════════════════════════════
# Génération de réponse avec Self-Check
# ══════════════════════════════════════════════════

async def _generate_with_self_check(
    context: ConversationContext,
    settings,
) -> AgentResponse:
    """
    Boucle de génération + vérification.
    Si le Self-Check échoue pour tone/language, on retry (max 2 fois).
    Si hallucination/scope/escalation → on escalade directement.
    """
    system_prompt = _build_system_prompt(context)

    # Construire les messages pour le LLM
    messages = [{"role": "system", "content": system_prompt}]

    # Ajouter l'historique de conversation
    for msg in context.history[:-1]:  # Exclure le dernier (= message courant)
        messages.append({
            "role": msg["role"],
            "content": msg["content"],
        })

    # Ajouter le message courant
    messages.append({"role": "user", "content": context.current_message})

    for attempt in range(1 + MAX_SELF_CHECK_RETRIES):
        # ── Génération de la réponse ──
        try:
            llm_response = await litellm.acompletion(
                model=settings.llm_model,
                messages=messages,
                max_tokens=500,
                temperature=0.7,
            )

            reply_text = llm_response.choices[0].message.content.strip()
            model_used = settings.llm_model
            tokens_used = llm_response.usage.total_tokens if llm_response.usage else 0

        except Exception as e:
            logger.error(f"❌ Erreur LLM (tentative {attempt + 1}): {e}")
            # Réponse de fallback
            return AgentResponse(
                text=_get_fallback_message(context.client_language),
                language=context.client_language,
                self_check_result=SelfCheckResult.NEEDS_ESCALATION,
                self_check_notes=f"Erreur LLM: {str(e)}",
                should_escalate=True,
                escalation_reason=f"Erreur technique LLM: {str(e)}",
                model_used="fallback",
                tokens_used=0,
            )

        # ── Self-Check ──
        check_result = await _run_self_check(
            context.current_message,
            reply_text,
            context.client_language,
            settings,
        )

        logger.info(
            f"🔎 Self-Check (tentative {attempt + 1}): "
            f"{check_result.self_check_result.value}"
        )

        await log_agent_action(
            conversation_id=context.conversation_id,
            action="self_check",
            details={
                "attempt": attempt + 1,
                "result": check_result.self_check_result.value,
                "notes": check_result.self_check_notes,
            },
        )

        # Passe le check → on retourne la réponse
        if check_result.self_check_result == SelfCheckResult.PASSED:
            return AgentResponse(
                text=reply_text,
                language=context.client_language,
                self_check_result=SelfCheckResult.PASSED,
                self_check_notes=check_result.self_check_notes,
                should_escalate=False,
                model_used=model_used,
                tokens_used=tokens_used,
            )

        # Fail critique → escalade immédiate, pas de retry
        if check_result.self_check_result in (
            SelfCheckResult.FAILED_HALLUCINATION,
            SelfCheckResult.FAILED_OUT_OF_SCOPE,
            SelfCheckResult.NEEDS_ESCALATION,
        ):
            logger.warning(
                f"🚨 Self-Check critique: {check_result.self_check_result.value} "
                f"→ escalade"
            )
            return AgentResponse(
                text=reply_text,
                language=context.client_language,
                self_check_result=check_result.self_check_result,
                self_check_notes=check_result.self_check_notes,
                should_escalate=True,
                escalation_reason=check_result.self_check_notes,
                model_used=model_used,
                tokens_used=tokens_used,
            )

        # Fail mineur (tone/language) → on retry avec instruction correctrice
        if attempt < MAX_SELF_CHECK_RETRIES:
            logger.info(
                f"🔄 Régénération (fail {check_result.self_check_result.value})"
            )
            correction = (
                f"Ta réponse précédente a échoué la vérification : "
                f"{check_result.self_check_notes}. "
                f"Régénère une réponse qui corrige ce problème. "
                f"Rappel : réponds en {context.client_language}."
            )
            messages.append({"role": "assistant", "content": reply_text})
            messages.append({"role": "user", "content": correction})

            await log_agent_action(
                conversation_id=context.conversation_id,
                action="self_check_retry",
                details={
                    "attempt": attempt + 1,
                    "reason": check_result.self_check_result.value,
                },
            )

    # Tous les retries épuisés → escalade
    logger.warning("🚨 Max retries Self-Check atteint → escalade")
    return AgentResponse(
        text=reply_text,
        language=context.client_language,
        self_check_result=check_result.self_check_result,
        self_check_notes="Max retries atteint: " + (check_result.self_check_notes or ""),
        should_escalate=True,
        escalation_reason="Le bot n'a pas réussi à générer une réponse conforme après plusieurs tentatives.",
        model_used=model_used,
        tokens_used=tokens_used,
    )


# ══════════════════════════════════════════════════
# Self-Check (appel LLM rapide)
# ══════════════════════════════════════════════════

async def _run_self_check(
    original_message: str,
    agent_reply: str,
    client_language: str,
    settings,
) -> AgentResponse:
    """
    Exécute le Self-Check via un modèle rapide (Haiku/GPT-4o-mini).
    Parse le JSON retourné pour déterminer si la réponse est valide.
    """
    import json
    import re

    prompt = _build_self_check_prompt(original_message, agent_reply, client_language)

    try:
        check_response = await litellm.acompletion(
            model=settings.llm_model_fast,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250,
            temperature=0.0,  # Déterministe pour l'évaluation
        )

        raw = check_response.choices[0].message.content.strip()

        # Nettoyer d'éventuelles balises de raisonnement (<think>...</think>)
        clean_raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()

        # Extraire le JSON entre la première accolade { et la dernière }
        start_idx = clean_raw.find("{")
        end_idx = clean_raw.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            json_str = clean_raw[start_idx : end_idx + 1]
        else:
            json_str = clean_raw

        result = json.loads(json_str)

        check_result_str = result.get("result", "passed")
        notes = result.get("notes", "")
        should_escalate = result.get("should_escalate", False)

        # Mapper le string vers l'enum
        try:
            self_check_enum = SelfCheckResult(check_result_str)
        except ValueError:
            logger.warning(f"⚠️ Self-Check result inconnu: {check_result_str}")
            self_check_enum = SelfCheckResult.PASSED

        return AgentResponse(
            text=agent_reply,
            language=client_language,
            self_check_result=self_check_enum,
            self_check_notes=notes,
            should_escalate=should_escalate,
        )

    except Exception as e:
        logger.error(f"❌ Erreur Self-Check: {e}")
        # En cas d'erreur du self-check, on laisse passer (fail-open)
        # plutôt que de bloquer le client
        return AgentResponse(
            text=agent_reply,
            language=client_language,
            self_check_result=SelfCheckResult.PASSED,
            self_check_notes=f"Self-Check error (fail-open): {str(e)}",
            should_escalate=False,
        )


# ══════════════════════════════════════════════════
# Escalade
# ══════════════════════════════════════════════════

async def _handle_escalation(
    context: ConversationContext,
    agent_response: AgentResponse,
) -> None:
    """
    Gère l'escalade : informe le client, crée le ticket Notion,
    logue l'action, et met à jour le statut de la conversation.
    """
    # 1. Informer le client
    escalation_message = _get_escalation_message(context.client_language, context.client_name)
    await send_text_message(context.client_phone, escalation_message)

    # 2. Créer le ticket Notion
    # Construire l'extrait de conversation (5 derniers messages)
    excerpt_lines = []
    for msg in context.history[-5:]:
        role_label = "Client" if msg["role"] == "user" else "Bot"
        excerpt_lines.append(f"[{role_label}] {msg['content']}")
    excerpt = "\n".join(excerpt_lines) if excerpt_lines else context.current_message

    ticket = EscalationTicket(
        client_name=context.client_name,
        client_phone=context.client_phone,
        summary=f"Escalade: {context.current_message[:80]}",
        conversation_excerpt=excerpt,
        reason=agent_response.escalation_reason or "Raison non spécifiée",
        priority=_determine_priority(agent_response, context),
    )

    ticket_url = await create_escalation_ticket(ticket)

    # 3. Loguer l'escalade
    await log_agent_action(
        conversation_id=context.conversation_id,
        action="escalation_triggered",
        status="escalated",
        details={
            "reason": agent_response.escalation_reason,
            "self_check_result": agent_response.self_check_result.value,
            "notion_ticket_url": ticket_url,
        },
    )

    # 4. Mettre à jour le statut de la conversation
    if context.conversation_id:
        await update_conversation_status(context.conversation_id, "escalated")

    # 5. Feedback Loop — loguer la question sans réponse
    await log_unanswered_question(
        question=context.current_message,
        client_phone=context.client_phone,
        conversation_id=context.conversation_id,
        context=excerpt,
    )

    logger.info(
        f"🚨 Escalade effectuée pour {context.client_name} — "
        f"raison: {agent_response.escalation_reason}"
    )


def _determine_priority(
    agent_response: AgentResponse, context: ConversationContext
) -> str:
    """
    Détermine la priorité du ticket d'escalade basée sur le contexte.
    """
    message_lower = context.current_message.lower()

    # Mots-clés indiquant une urgence
    urgent_keywords = ["avocat", "justice", "juridique", "double débit", "fraude", "volé"]
    high_keywords = ["remboursement", "rembourser", "inacceptable", "scandaleux"]

    if any(kw in message_lower for kw in urgent_keywords):
        return "urgent"
    elif any(kw in message_lower for kw in high_keywords):
        return "high"
    elif agent_response.self_check_result in (
        SelfCheckResult.FAILED_HALLUCINATION,
        SelfCheckResult.NEEDS_ESCALATION,
    ):
        return "high"
    else:
        return "medium"


# ══════════════════════════════════════════════════
# Messages de fallback / escalade
# ══════════════════════════════════════════════════

def _get_escalation_message(language: str, name: str = "") -> str:
    """Message envoyé au client lors d'une escalade, dans sa langue."""
    name_part = f" {name}" if name else ""

    messages = {
        "fr": (
            f"Merci pour votre patience{name_part}. 🙏\n\n"
            f"Je vais transmettre votre demande à notre équipe spécialisée "
            f"qui pourra vous aider directement.\n\n"
            f"Vous recevrez une réponse sous 24h ouvrées."
        ),
        "en": (
            f"Thank you for your patience{name_part}. 🙏\n\n"
            f"I'm forwarding your request to our specialized team "
            f"who will be able to help you directly.\n\n"
            f"You'll receive a response within 24 business hours."
        ),
    }

    return messages.get(language, messages["fr"])


def _get_fallback_message(language: str) -> str:
    """Message de fallback en cas d'erreur technique."""
    messages = {
        "fr": (
            "Désolé, je rencontre un problème technique. 😔\n\n"
            "Je transfère votre demande à notre équipe qui vous répondra "
            "sous 24h ouvrées. Merci de votre compréhension. 🙏"
        ),
        "en": (
            "Sorry, I'm experiencing a technical issue. 😔\n\n"
            "I'm forwarding your request to our team who will respond "
            "within 24 business hours. Thank you for your understanding. 🙏"
        ),
    }

    return messages.get(language, messages["fr"])
