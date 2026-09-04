"""
Modèles Pydantic pour le WhatsApp Agentic Support Bot.
Définit les structures de données pour les payloads WhatsApp,
les messages internes, et les réponses de l'agent.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from enum import Enum


# ──────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────

class MessageRole(str, Enum):
    """Rôle de l'auteur du message."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ConversationStatus(str, Enum):
    """Statut d'une conversation."""
    ACTIVE = "active"
    ESCALATED = "escalated"
    RESOLVED = "resolved"


class AgentActionStatus(str, Enum):
    """Statut d'une action loguée par l'agent."""
    SUCCESS = "success"
    ERROR = "error"
    ESCALATED = "escalated"


class SelfCheckResult(str, Enum):
    """Résultat de l'auto-vérification."""
    PASSED = "passed"
    FAILED_HALLUCINATION = "failed_hallucination"
    FAILED_TONE = "failed_tone"
    FAILED_LANGUAGE = "failed_language"
    FAILED_OUT_OF_SCOPE = "failed_out_of_scope"
    NEEDS_ESCALATION = "needs_escalation"


# ──────────────────────────────────────────────────
# WhatsApp Webhook Payload Models
# ──────────────────────────────────────────────────

class WhatsAppProfile(BaseModel):
    """Profil de l'expéditeur WhatsApp."""
    name: Optional[str] = ""

    model_config = {"extra": "ignore"}


class WhatsAppContact(BaseModel):
    """Contact WhatsApp dans le webhook."""
    profile: Optional[WhatsAppProfile] = None
    wa_id: Optional[str] = None

    model_config = {"extra": "ignore"}


class WhatsAppTextContent(BaseModel):
    """Contenu texte d'un message WhatsApp."""
    body: str

    model_config = {"extra": "ignore"}


class WhatsAppMessage(BaseModel):
    """Message individuel dans le webhook WhatsApp."""
    from_: str = Field(alias="from")
    id: str
    timestamp: str
    text: Optional[WhatsAppTextContent] = None
    type: str

    model_config = {"populate_by_name": True, "extra": "ignore"}


class WhatsAppMetadata(BaseModel):
    """Métadonnées du webhook WhatsApp."""
    display_phone_number: Optional[str] = None
    phone_number_id: Optional[str] = None

    model_config = {"extra": "ignore"}


class WhatsAppValue(BaseModel):
    """Valeur contenue dans un changement webhook."""
    messaging_product: Optional[str] = "whatsapp"
    metadata: Optional[WhatsAppMetadata] = None
    contacts: Optional[list[WhatsAppContact]] = None
    messages: Optional[list[WhatsAppMessage]] = None
    statuses: Optional[list[dict]] = None

    model_config = {"extra": "ignore"}


class WhatsAppChange(BaseModel):
    """Changement dans le webhook WhatsApp."""
    value: WhatsAppValue
    field: Optional[str] = None

    model_config = {"extra": "ignore"}


class WhatsAppEntry(BaseModel):
    """Entrée du webhook WhatsApp."""
    id: Optional[str] = None
    changes: list[WhatsAppChange]

    model_config = {"extra": "ignore"}


class WhatsAppWebhookPayload(BaseModel):
    """Payload complet du webhook WhatsApp Cloud API."""
    object: Optional[str] = None
    entry: list[WhatsAppEntry]

    model_config = {"extra": "ignore"}


# ──────────────────────────────────────────────────
# Internal Models
# ──────────────────────────────────────────────────

class IncomingMessage(BaseModel):
    """Message entrant normalisé (après parsing du webhook)."""
    phone: str
    name: str
    text: str
    whatsapp_message_id: str
    timestamp: datetime


class AgentResponse(BaseModel):
    """Réponse générée par l'agent."""
    text: str
    language: str
    self_check_result: SelfCheckResult
    self_check_notes: Optional[str] = None
    should_escalate: bool = False
    escalation_reason: Optional[str] = None
    model_used: str = ""
    tokens_used: int = 0


class ConversationContext(BaseModel):
    """Contexte complet d'une conversation pour l'agent."""
    client_phone: str
    client_name: str
    client_language: str = "fr"
    conversation_id: Optional[str] = None
    history: list[dict] = Field(default_factory=list)
    current_message: str = ""


class EscalationTicket(BaseModel):
    """Ticket d'escalade à créer dans Notion."""
    client_name: str
    client_phone: str
    summary: str
    conversation_excerpt: str
    reason: str
    priority: str = "medium"  # low, medium, high, urgent
