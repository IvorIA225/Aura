"""
Tool Supabase — Mémoire persistante du bot.

Couche 3 du Framework WAT : gère le stockage des conversations,
messages, logs d'actions, et questions sans réponse (Feedback Loop).
"""

import json
import logging
from typing import Optional
from datetime import datetime, timezone

from app.config import get_settings

logger = logging.getLogger(__name__)

# ── Client Supabase (lazy init) ──

_supabase_client = None


def _get_client():
    """Initialise le client Supabase en lazy (au premier appel)."""
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_key:
            raise RuntimeError(
                "SUPABASE_URL et SUPABASE_KEY doivent être configurés dans .env"
            )
        _supabase_client = create_client(settings.supabase_url, settings.supabase_key)
    return _supabase_client


# ──────────────────────────────────────────────────
# Conversations
# ──────────────────────────────────────────────────

async def get_or_create_conversation(
    phone: str, name: str = "", language: str = "fr"
) -> dict:
    """
    Récupère la conversation active d'un client, ou en crée une nouvelle.

    Returns:
        dict avec les champs de la conversation (id, client_phone, status, etc.)
    """
    client = _get_client()

    # Chercher une conversation active pour ce numéro
    result = (
        client.table("conversations")
        .select("*")
        .eq("client_phone", phone)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if result.data:
        conversation = result.data[0]
        # Mettre à jour le nom et la langue si nécessaire
        if name and conversation.get("client_name") != name:
            client.table("conversations").update(
                {"client_name": name, "client_language": language}
            ).eq("id", conversation["id"]).execute()
            conversation["client_name"] = name
            conversation["client_language"] = language
        logger.info(f"📂 Conversation existante trouvée: {conversation['id']}")
        return conversation

    # Créer une nouvelle conversation
    new_conv = (
        client.table("conversations")
        .insert({
            "client_phone": phone,
            "client_name": name,
            "client_language": language,
            "status": "active",
        })
        .execute()
    )

    conversation = new_conv.data[0]
    logger.info(f"📂 Nouvelle conversation créée: {conversation['id']}")
    return conversation


async def update_conversation_status(conversation_id: str, status: str) -> None:
    """Met à jour le statut d'une conversation (active, escalated, resolved)."""
    client = _get_client()
    client.table("conversations").update(
        {"status": status}
    ).eq("id", conversation_id).execute()
    logger.info(f"📂 Conversation {conversation_id} → {status}")


# ──────────────────────────────────────────────────
# Messages
# ──────────────────────────────────────────────────

async def save_message(
    conversation_id: str,
    role: str,
    content: str,
    model_used: str = None,
    tokens_used: int = None,
    self_check_result: str = None,
    self_check_notes: str = None,
) -> dict:
    """
    Sauvegarde un message dans l'historique de la conversation.

    Args:
        conversation_id: UUID de la conversation
        role: 'user', 'assistant', ou 'system'
        content: Contenu du message
        model_used: (assistant only) Modèle LLM utilisé
        tokens_used: (assistant only) Tokens consommés
        self_check_result: (assistant only) Résultat du Self-Check
        self_check_notes: (assistant only) Notes du Self-Check
    """
    client = _get_client()

    message_data = {
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
    }

    # Ajouter les métadonnées agent si présentes
    if model_used is not None:
        message_data["model_used"] = model_used
    if tokens_used is not None:
        message_data["tokens_used"] = tokens_used
    if self_check_result is not None:
        message_data["self_check_result"] = self_check_result
    if self_check_notes is not None:
        message_data["self_check_notes"] = self_check_notes

    result = client.table("messages").insert(message_data).execute()
    return result.data[0]


async def get_conversation_history(phone: str, limit: int = 20) -> list[dict]:
    """
    Charge les N derniers messages de la conversation active d'un client.

    Returns:
        Liste de dicts {role, content, created_at} ordonnés chronologiquement.
    """
    client = _get_client()

    # Trouver la conversation active
    conv_result = (
        client.table("conversations")
        .select("id")
        .eq("client_phone", phone)
        .eq("status", "active")
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )

    if not conv_result.data:
        return []

    conversation_id = conv_result.data[0]["id"]

    # Charger les messages
    msg_result = (
        client.table("messages")
        .select("role, content, created_at")
        .eq("conversation_id", conversation_id)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    # Retourner dans l'ordre chronologique (du plus ancien au plus récent)
    return list(reversed(msg_result.data)) if msg_result.data else []


# ──────────────────────────────────────────────────
# Agent Logs
# ──────────────────────────────────────────────────

async def log_agent_action(
    conversation_id: str,
    action: str,
    status: str = "success",
    details: dict = None,
) -> None:
    """
    Logge une action de l'agent pour monitoring et debugging.

    Actions typiques : 'response_sent', 'self_check_fail', 'self_check_retry',
                       'escalation_triggered', 'language_detected', etc.
    """
    client = _get_client()

    log_data = {
        "conversation_id": conversation_id,
        "action": action,
        "status": status,
    }
    if details:
        log_data["details"] = json.dumps(details)

    try:
        client.table("agent_logs").insert(log_data).execute()
    except Exception as e:
        # Le logging ne doit jamais faire planter le bot
        logger.error(f"Erreur logging agent action: {e}")


# ──────────────────────────────────────────────────
# Self-Improvement Loop (Questions sans réponse)
# ──────────────────────────────────────────────────

async def log_unanswered_question(
    question: str,
    client_phone: str = None,
    conversation_id: str = None,
    detected_intent: str = None,
    context: str = None,
) -> None:
    """
    Enregistre une question à laquelle le bot n'a pas su répondre.
    Ces entrées alimentent la boucle d'auto-amélioration :
    un humain review → ajoute l'info à knowledge.md → le bot s'améliore.
    """
    client = _get_client()

    try:
        client.table("unanswered_questions").insert({
            "question": question,
            "client_phone": client_phone,
            "conversation_id": conversation_id,
            "detected_intent": detected_intent,
            "context": context,
            "status": "pending",
        }).execute()
        logger.info(f"📝 Question sans réponse loguée: {question[:60]}...")
    except Exception as e:
        logger.error(f"Erreur logging unanswered question: {e}")


# ──────────────────────────────────────────────────
# Dashboard API (pour main.py /api/*)
# ──────────────────────────────────────────────────

async def get_dashboard_stats() -> dict:
    """Retourne les statistiques globales pour le dashboard admin."""
    client = _get_client()

    # Compter les conversations par statut
    all_convs = client.table("conversations").select("status").execute()
    convs = all_convs.data or []

    total = len(convs)
    active = sum(1 for c in convs if c["status"] == "active")
    escalated = sum(1 for c in convs if c["status"] == "escalated")
    resolved = sum(1 for c in convs if c["status"] == "resolved")

    # Compter les messages
    msg_count = client.table("messages").select("id", count="exact").execute()

    # Compter les questions sans réponse en attente
    unanswered = (
        client.table("unanswered_questions")
        .select("id", count="exact")
        .eq("status", "pending")
        .execute()
    )

    return {
        "conversations": {
            "total": total,
            "active": active,
            "escalated": escalated,
            "resolved": resolved,
        },
        "messages_total": msg_count.count or 0,
        "unanswered_pending": unanswered.count or 0,
    }


async def get_conversations_list(
    status: str = None, limit: int = 50
) -> list[dict]:
    """Liste les conversations pour le dashboard, avec filtrage optionnel."""
    client = _get_client()

    query = client.table("conversations").select("*").order("updated_at", desc=True).limit(limit)

    if status:
        query = query.eq("status", status)

    result = query.execute()
    return result.data or []


async def get_unanswered_questions(
    status: str = "pending", limit: int = 50
) -> list[dict]:
    """Liste les questions sans réponse pour la boucle d'amélioration."""
    client = _get_client()

    result = (
        client.table("unanswered_questions")
        .select("*")
        .eq("status", status)
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )

    return result.data or []
