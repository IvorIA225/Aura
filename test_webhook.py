"""
Script de test — Simule un webhook WhatsApp entrant.

Usage:
    python test_webhook.py

Envoie un faux payload WhatsApp au serveur local pour tester
le pipeline complet sans avoir besoin d'un vrai compte WhatsApp.
"""

import httpx
import json
import time
import sys

BASE_URL = "http://localhost:8000"


def test_health():
    """Test le endpoint /health."""
    print("─" * 50)
    print("🏥 Test /health...")
    r = httpx.get(f"{BASE_URL}/health")
    print(f"   Status: {r.status_code}")
    print(f"   Body: {r.json()}")
    assert r.status_code == 200
    print("   ✅ OK\n")


def test_webhook_verify():
    """Test la vérification du webhook (GET)."""
    print("─" * 50)
    print("🔐 Test GET /webhook (verify)...")
    r = httpx.get(
        f"{BASE_URL}/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "your_verify_token_here",  # Doit matcher .env
            "hub.challenge": "test_challenge_123",
        },
    )
    print(f"   Status: {r.status_code}")
    print(f"   Body: {r.text}")
    if r.status_code == 200:
        print("   ✅ Webhook vérifié\n")
    else:
        print("   ⚠️ Vérification échouée (vérifier WHATSAPP_VERIFY_TOKEN)\n")


def test_webhook_message(text: str = "Bonjour, je voudrais suivre ma commande #12345"):
    """Simule un message WhatsApp entrant."""
    print("─" * 50)
    print(f"📨 Test POST /webhook (message: '{text[:50]}...')")

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "BUSINESS_ACCOUNT_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "33100000000",
                                "phone_number_id": "PHONE_NUMBER_ID",
                            },
                            "contacts": [
                                {
                                    "profile": {"name": "Jean Test"},
                                    "wa_id": "33612345678",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "33612345678",
                                    "id": f"wamid.test_{int(time.time())}",
                                    "timestamp": str(int(time.time())),
                                    "text": {"body": text},
                                    "type": "text",
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    r = httpx.post(
        f"{BASE_URL}/webhook",
        json=payload,
        timeout=30.0,
    )
    print(f"   Status: {r.status_code}")
    print("   ✅ Webhook traité\n")


# ── Scénarios de test ──

TEST_MESSAGES = [
    # FAQ standard
    "Bonjour, quels sont vos délais de livraison pour la France ?",
    # Suivi commande
    "Je voudrais savoir où en est ma commande #12345",
    # Demande d'escalade (remboursement)
    "Je veux un remboursement immédiat, le produit est défectueux !",
    # Anglais
    "Hello, what is your return policy?",
    # Hors sujet
    "Quelle est la capitale du Pérou ?",
    # Client mécontent
    "C'EST SCANDALEUX ! Mon colis n'arrive JAMAIS ! Je vais contacter mon avocat !",
]


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Test du WhatsApp Agentic Support Bot")
    print("=" * 50)
    print()

    try:
        test_health()
    except Exception as e:
        print(f"❌ Le serveur ne répond pas sur {BASE_URL}")
        print(f"   Lancez d'abord: uvicorn app.main:app --reload")
        print(f"   Erreur: {e}")
        sys.exit(1)

    test_webhook_verify()

    # Si un argument est passé, l'utiliser comme message
    if len(sys.argv) > 1:
        custom_message = " ".join(sys.argv[1:])
        test_webhook_message(custom_message)
    else:
        # Lancer tous les scénarios
        for i, msg in enumerate(TEST_MESSAGES, 1):
            print(f"── Scénario {i}/{len(TEST_MESSAGES)} ──")
            test_webhook_message(msg)
            time.sleep(2)  # Pause entre les messages

    print("=" * 50)
    print("🏁 Tests terminés !")
    print("=" * 50)
