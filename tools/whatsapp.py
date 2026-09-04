"""
Tool WhatsApp — Envoi et réception de messages via WhatsApp Cloud API.

Couche 3 du Framework WAT : script déterministe qui ne fait qu'une chose
(communiquer avec l'API WhatsApp) sans connaître le contexte métier.
"""

import httpx
import logging
from typing import Optional

from app.config import get_settings
from app.models import (
    WhatsAppWebhookPayload,
    IncomingMessage,
)
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

WHATSAPP_API_BASE = "https://graph.facebook.com/v21.0"


def parse_incoming_message(payload: WhatsAppWebhookPayload) -> Optional[IncomingMessage]:
    """
    Parse le payload webhook WhatsApp et extrait le message texte.
    
    Retourne None si le payload ne contient pas de message texte
    (ex: statut de livraison, message multimédia non supporté).
    """
    try:
        for entry in payload.entry:
            for change in entry.changes:
                value = change.value
                if not value.messages:
                    continue

                message = value.messages[0]
                sender_name = ""
                if value.contacts and len(value.contacts) > 0:
                    c = value.contacts[0]
                    if c.profile and c.profile.name:
                        sender_name = c.profile.name

                # On ne gère que les messages texte pour le PoC
                if message.type != "text" or not message.text:
                    logger.info(
                        f"Message non-texte ignoré (type: {message.type}) "
                        f"de {message.from_}"
                    )
                    return None

                return IncomingMessage(
                    phone=message.from_,
                    name=sender_name,
                    text=message.text.body,
                    whatsapp_message_id=message.id,
                    timestamp=datetime.fromtimestamp(
                        int(message.timestamp), tz=timezone.utc
                    ),
                )
    except Exception as e:
        logger.error(f"Erreur parsing webhook WhatsApp: {e}")
        return None

    return None


async def send_text_message(phone: str, text: str) -> bool:
    """
    Envoie un message texte via WhatsApp Cloud API.

    Args:
        phone: Numéro de téléphone du destinataire (format international, ex: 33612345678)
        text: Contenu du message texte

    Returns:
        True si le message a été envoyé avec succès, False sinon
    """
    settings = get_settings()

    url = f"{WHATSAPP_API_BASE}/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": text},
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                logger.info(f"✅ Message envoyé à {phone}")
                return True
            else:
                logger.error(
                    f"❌ Erreur envoi WhatsApp ({response.status_code}): "
                    f"{response.text}"
                )
                return False
    except httpx.TimeoutException:
        logger.error(f"⏱️ Timeout envoi WhatsApp à {phone}")
        return False
    except Exception as e:
        logger.error(f"❌ Exception envoi WhatsApp: {e}")
        return False


async def send_media_message(
    phone: str, media_url: str, media_type: str = "image", caption: str = ""
) -> bool:
    """
    Envoie un message média (image, document) via WhatsApp Cloud API.

    Args:
        phone: Numéro du destinataire
        media_url: URL publique du média
        media_type: Type de média ('image', 'document', 'video')
        caption: Légende optionnelle
    """
    settings = get_settings()

    url = f"{WHATSAPP_API_BASE}/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }

    media_object = {"link": media_url}
    if caption:
        media_object["caption"] = caption

    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": media_type,
        media_type: media_object,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=headers, json=payload)

            if response.status_code == 200:
                logger.info(f"✅ Média ({media_type}) envoyé à {phone}")
                return True
            else:
                logger.error(
                    f"❌ Erreur envoi média WhatsApp ({response.status_code}): "
                    f"{response.text}"
                )
                return False
    except Exception as e:
        logger.error(f"❌ Exception envoi média WhatsApp: {e}")
        return False


async def mark_as_read(message_id: str) -> bool:
    """
    Marque un message comme lu sur WhatsApp (double coche bleue).
    Améliore l'expérience utilisateur en montrant que le message a été reçu.
    """
    settings = get_settings()

    url = f"{WHATSAPP_API_BASE}/{settings.whatsapp_phone_number_id}/messages"
    headers = {
        "Authorization": f"Bearer {settings.whatsapp_access_token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, headers=headers, json=payload)
            return response.status_code == 200
    except Exception:
        return False
