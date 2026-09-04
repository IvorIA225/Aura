"""
Configuration centralisée du WhatsApp Agentic Support Bot.
Charge les variables d'environnement et expose les settings via Pydantic.

Principe de sécurité (cf. Securite_et_Permissions_des_Outils.md) :
- Les secrets sont dans .env, jamais dans le code source.
- Les clés API sont scopées au minimum nécessaire.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # ── WhatsApp Cloud API ──
    whatsapp_verify_token: str = ""
    whatsapp_access_token: str = ""
    whatsapp_phone_number_id: str = ""

    # ── LLM Configuration (LiteLLM) ──
    # Modèle principal pour la génération de réponses
    llm_model: str = "groq/qwen/qwen3.8-27b"
    # Modèle rapide/pas cher pour le Self-Check et la détection de langue
    llm_model_fast: str = "groq/groq/compound-mini"
    # API keys (LiteLLM les détecte automatiquement via env vars)
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # ── Supabase ──
    supabase_url: str = ""
    supabase_key: str = ""

    # ── Notion (Escalade) ──
    notion_api_key: str = ""
    notion_database_id: str = ""

    # ── App ──
    environment: str = "development"
    log_level: str = "INFO"

    # ── Paths ──
    knowledge_path: str = "knowledge.md"
    workflows_dir: str = "workflows"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


@lru_cache()
def get_settings() -> Settings:
    """
    Singleton pour les settings — chargé une seule fois.
    Utilise @lru_cache pour éviter de relire .env à chaque requête.
    """
    return Settings()
