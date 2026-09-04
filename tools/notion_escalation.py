"""
Tool Notion — Création de tickets d'escalade dans Notion.

Couche 3 du Framework WAT : gère uniquement la communication avec l'API Notion
pour créer des pages dans la base "Tickets Support".
"""

import logging
from typing import Optional

from app.config import get_settings
from app.models import EscalationTicket

logger = logging.getLogger(__name__)

# ── Client Notion (lazy init) ──

_notion_client = None


def _get_client():
    """Initialise le client Notion en lazy."""
    global _notion_client
    if _notion_client is None:
        from notion_client import Client
        settings = get_settings()
        if not settings.notion_api_key:
            raise RuntimeError("NOTION_API_KEY doit être configuré dans .env")
        _notion_client = Client(auth=settings.notion_api_key)
    return _notion_client


# ── Mapping priorité → emoji + couleur Notion ──

PRIORITY_MAP = {
    "urgent": {"emoji": "🔴", "color": "red"},
    "high": {"emoji": "🟠", "color": "orange"},
    "medium": {"emoji": "🟡", "color": "yellow"},
    "low": {"emoji": "🟢", "color": "green"},
}


async def create_escalation_ticket(ticket: EscalationTicket) -> Optional[str]:
    """
    Crée un ticket d'escalade dans la base Notion "Tickets Support".

    Args:
        ticket: EscalationTicket avec toutes les infos nécessaires

    Returns:
        L'URL de la page Notion créée, ou None en cas d'erreur.
    """
    settings = get_settings()

    if not settings.notion_database_id:
        logger.warning("⚠️ NOTION_DATABASE_ID non configuré — escalade non enregistrée dans Notion")
        return None

    try:
        client = _get_client()
        priority_info = PRIORITY_MAP.get(ticket.priority, PRIORITY_MAP["medium"])

        # Construire la page Notion
        new_page = client.pages.create(
            parent={"database_id": settings.notion_database_id},
            icon={"type": "emoji", "emoji": priority_info["emoji"]},
            properties={
                "Name": {
                    "title": [
                        {
                            "text": {
                                "content": f"[{ticket.priority.upper()}] {ticket.summary}"
                            }
                        }
                    ]
                },
                "Client": {
                    "rich_text": [
                        {
                            "text": {
                                "content": f"{ticket.client_name} ({ticket.client_phone})"
                            }
                        }
                    ]
                },
                "Priorité": {
                    "select": {"name": ticket.priority.capitalize()}
                },
                "Statut": {
                    "select": {"name": "Nouveau"}
                },
                "Raison": {
                    "rich_text": [
                        {"text": {"content": ticket.reason}}
                    ]
                },
            },
            # Contenu de la page (body)
            children=[
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "📋 Contexte de la conversation"}}]
                    },
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": ticket.conversation_excerpt}}]
                    },
                },
                {
                    "object": "block",
                    "type": "divider",
                    "divider": {},
                },
                {
                    "object": "block",
                    "type": "heading_2",
                    "heading_2": {
                        "rich_text": [{"text": {"content": "🚨 Raison de l'escalade"}}]
                    },
                },
                {
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": ticket.reason}}]
                    },
                },
                {
                    "object": "block",
                    "type": "divider",
                    "divider": {},
                },
                {
                    "object": "block",
                    "type": "callout",
                    "callout": {
                        "icon": {"type": "emoji", "emoji": "📱"},
                        "rich_text": [
                            {
                                "text": {
                                    "content": f"Client : {ticket.client_name}\n"
                                               f"Téléphone : {ticket.client_phone}\n"
                                               f"Priorité : {priority_info['emoji']} {ticket.priority.upper()}"
                                }
                            }
                        ],
                    },
                },
            ],
        )

        page_url = new_page.get("url", "")
        logger.info(
            f"🎫 Ticket Notion créé: {ticket.summary} "
            f"(priorité: {ticket.priority}) → {page_url}"
        )
        return page_url

    except Exception as e:
        logger.error(f"❌ Erreur création ticket Notion: {e}", exc_info=True)
        return None
