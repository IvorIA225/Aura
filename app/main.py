"""
Point d'entrée FastAPI — WhatsApp Agentic Support Bot.

Routes :
- GET  /webhook  → Vérification WhatsApp (challenge handshake)
- POST /webhook  → Réception des messages entrants
- GET  /health   → Healthcheck pour Render
- GET  /admin    → Dashboard admin (sert les fichiers statiques)
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, Query, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import get_settings
from app.models import WhatsAppWebhookPayload
from app.agent import process_message
from tools.whatsapp import parse_incoming_message, mark_as_read

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown events."""
    settings = get_settings()
    logger.info("🤖 WhatsApp Agentic Support Bot démarré")
    logger.info(f"   Environnement : {settings.environment}")
    logger.info(f"   Modèle principal : {settings.llm_model}")
    logger.info(f"   Modèle rapide : {settings.llm_model_fast}")

    if not settings.whatsapp_access_token:
        logger.warning("⚠️  WHATSAPP_ACCESS_TOKEN non configuré !")
    if not settings.supabase_url:
        logger.warning("⚠️  SUPABASE_URL non configuré !")

    yield
    logger.info("🛑 Bot arrêté")


app = FastAPI(
    title="WhatsApp Agentic Support Bot",
    description="Support client e-commerce automatisé via WhatsApp — Framework WAT",
    version="0.1.0",
    lifespan=lifespan,
)


# ──────────────────────────────────────────────────
# Route : Healthcheck
# ──────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Healthcheck endpoint pour Render et monitoring."""
    return {
        "status": "ok",
        "service": "whatsapp-support-bot",
        "brand": "Ella's Fashion House",
        "version": "1.0.0",
    }


# ──────────────────────────────────────────────────
# Route : Webhook Verification (GET)
# ──────────────────────────────────────────────────

@app.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    Vérification du webhook WhatsApp Cloud API.
    Meta envoie un GET avec un challenge pour vérifier que le webhook est valide.
    """
    settings = get_settings()

    if hub_mode == "subscribe" and hub_verify_token == settings.whatsapp_verify_token:
        logger.info("✅ Webhook vérifié avec succès")
        return Response(content=hub_challenge, media_type="text/plain")

    logger.warning(
        f"❌ Vérification webhook échouée — "
        f"mode={hub_mode}, token={'***' if hub_verify_token else 'None'}"
    )
    raise HTTPException(status_code=403, detail="Verification failed")


# ──────────────────────────────────────────────────
# Route : Webhook Messages (POST)
# ──────────────────────────────────────────────────

@app.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Reçoit les messages WhatsApp entrants.
    
    Flow (Framework WAT) :
    1. Parse le payload WhatsApp
    2. Marque le message comme lu (UX)
    3. Délègue à l'agent en tâche de fond (BackgroundTasks)
    4. Retourne 200 immédiatement (< 100ms) pour éviter les retries Meta
    """
    try:
        body = await request.json()
        payload = WhatsAppWebhookPayload(**body)
    except Exception as e:
        logger.error(f"Payload webhook invalide: {e}")
        return Response(status_code=200)  # WhatsApp attend toujours un 200

    # Parser le message entrant
    incoming = parse_incoming_message(payload)

    if not incoming:
        # Pas un message texte (statut de livraison, etc.) — on ignore
        return Response(status_code=200)

    logger.info(
        f"📨 Message reçu de {incoming.name} ({incoming.phone}): "
        f"{incoming.text[:80]}..."
    )

    # Marquer comme lu (double coche bleue)
    await mark_as_read(incoming.whatsapp_message_id)

    # Traitement non-bloquant en tâche de fond (production-grade)
    background_tasks.add_task(process_message, incoming)

    # WhatsApp exige un 200 immédiat, sinon il renvoie le message en boucle
    return Response(status_code=200)


# ──────────────────────────────────────────────────
# Route : Dashboard Admin
# ──────────────────────────────────────────────────

# Servir les fichiers statiques du dashboard
try:
    app.mount("/admin", StaticFiles(directory="dashboard", html=True), name="dashboard")
except Exception:
    logger.info("📊 Dashboard non trouvé — /admin désactivé pour le moment")


# ──────────────────────────────────────────────────
# Route : API Dashboard (données pour le frontend)
# ──────────────────────────────────────────────────

@app.get("/api/stats")
async def get_stats():
    """Retourne les statistiques pour le dashboard admin."""
    try:
        from tools.supabase_db import get_dashboard_stats
        stats = await get_dashboard_stats()
        return JSONResponse(content=stats)
    except Exception as e:
        logger.error(f"Erreur récupération stats: {e}")
        return JSONResponse(
            content={"error": "Stats unavailable"},
            status_code=500,
        )


@app.get("/api/conversations")
async def get_conversations(
    status: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Liste les conversations pour le dashboard."""
    try:
        from tools.supabase_db import get_conversations_list
        conversations = await get_conversations_list(status=status, limit=limit)
        return JSONResponse(content=conversations)
    except Exception as e:
        logger.error(f"Erreur récupération conversations: {e}")
        return JSONResponse(content=[], status_code=500)


@app.get("/api/unanswered")
async def get_unanswered(
    status: str = Query("pending"),
    limit: int = Query(50, ge=1, le=200),
):
    """Liste les questions sans réponse (Self-Improvement Loop)."""
    try:
        from tools.supabase_db import get_unanswered_questions
        questions = await get_unanswered_questions(status=status, limit=limit)
        return JSONResponse(content=questions)
    except Exception as e:
        logger.error(f"Erreur récupération unanswered: {e}")
        return JSONResponse(content=[], status_code=500)
