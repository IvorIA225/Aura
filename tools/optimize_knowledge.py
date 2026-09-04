"""
Script d'optimisation et d'auto-amélioration de la base de connaissances (Framework WAT).

Règle n°3 (GEMINI.md) :
L'Agent est capable de loguer les cas où il n'a pas su répondre,
pour qu'un script d'optimisation puisse suggérer des mises à jour du fichier knowledge.md.
"""

import sys
sys.stdout.reconfigure(encoding="utf-8")
import asyncio
from pathlib import Path
import litellm

from app.config import get_settings
from tools.supabase_db import _get_client


async def optimize_knowledge(apply_changes: bool = False):
    settings = get_settings()
    client = _get_client()

    # 1. Récupérer les questions sans réponse en attente
    res = (
        client.table("unanswered_questions")
        .select("*")
        .eq("status", "pending")
        .order("created_at", desc=False)
        .execute()
    )

    questions = res.data
    if not questions:
        print("✅ Aucune question sans réponse en attente dans Supabase.")
        return

    print(f"\n📊 {len(questions)} question(s) sans réponse détectée(s) :")
    for q in questions:
        print(f" - [{q.get('created_at', '')[:10]}] {q.get('question')}")

    # 2. Charger le fichier knowledge.md actuel
    knowledge_path = Path(settings.knowledge_path)
    current_knowledge = knowledge_path.read_text(encoding="utf-8") if knowledge_path.exists() else ""

    prompt = f"""Tu es un expert en Knowledge Base Engineering pour le support client e-commerce.
Voici la liste des questions posées par des clients sur WhatsApp pour lesquelles le bot n'avait pas l'information :

{chr(10).join(f"- {q.get('question')}" for q in questions)}

Voici la base de connaissances actuelle (knowledge.md) :
---
{current_knowledge}
---

TÂCHE :
1. Analyse les manques d'informations soulevés par ces questions.
2. Rédige de nouvelles sections ou entrées FAQ au format Markdown, prêtes à être ajoutées à knowledge.md.
3. Utilise des balises [À REMPLIR : ...] si certaines informations dépendent des choix du marchand (ex: tarifs exacts, politique spécifique).

Réponds UNIQUEMENT avec les nouveaux blocs Markdown à intégrer dans knowledge.md.
"""

    print("\n🧠 Analyse par l'IA et génération des suggestions d'amélioration...")
    response = await litellm.acompletion(
        model=settings.llm_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=600,
        temperature=0.3,
    )

    suggestions = response.choices[0].message.content.strip()
    print("\n💡 Suggestions d'ajouts pour knowledge.md :\n")
    print(suggestions)

    # 3. Application si demandée
    if apply_changes:
        new_content = current_knowledge + "\n\n" + suggestions + "\n"
        knowledge_path.write_text(new_content, encoding="utf-8")
        print("\n✅ knowledge.md a été mis à jour !")

        # Marquer les questions comme traitées dans Supabase
        ids = [q["id"] for q in questions if "id" in q]
        if ids:
            for qid in ids:
                client.table("unanswered_questions").update({"status": "resolved"}).eq("id", qid).execute()
            print(f"✅ {len(ids)} question(s) marquée(s) comme résolue(s) dans Supabase.")
    else:
        print("\nℹ️ Pour appliquer automatiquement ces ajouts, lancez :")
        print("   python tools/optimize_knowledge.py --apply")


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    asyncio.run(optimize_knowledge(apply_changes=apply))
