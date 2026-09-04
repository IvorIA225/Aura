# 🤖 WhatsApp Agentic Support Bot (Framework WAT)

## Contexte du Projet
Ce projet est un **PoC (Proof of Concept)** de support client automatisé sur WhatsApp.
L'objectif est de démontrer l'efficacité de l'Agentic Engineering via le framework **WAT (Workflows, Agents, Tools)**. Le système inclut une architecture d'**auto-correction** et d'**amélioration continue**.

## Architecture & Stack
- **Interface :** WhatsApp Cloud API (Meta).
- **Agent (Backend) :** À DÉFINIR (Python ou Node.js) déployable sur Modal, Render ou Vercel.
- **Tools :** Fonctions modulaires (interrogation Supabase, etc.).
- **Mémoire & Logs :** Supabase (pour analyser les conversations).

## Règles de Développement (Agentic Engineering)
1. **Séparation Stricte (Framework WAT) :** 
   - Les règles sont dans `workflows/whatsapp_support.md`.
   - Les connaissances métier sont dans `knowledge.md`.
2. **Auto-Correction (Self-Reflection) :**
   - Implémenter un mécanisme de "Double-Check". L'Agent doit évaluer sa propre réponse face aux contraintes du Workflow avant de l'envoyer au client.
3. **Auto-Amélioration (Feedback Loop) :**
   - L'Agent doit être capable de loguer les cas où il n'a pas su répondre, pour qu'un script d'optimisation puisse suggérer des mises à jour du fichier `knowledge.md`.
4. **Tooling :** Chaque action externe se fait via un script dédié dans `/tools`.

## Objectif Immédiat pour l'Agent
Dès que l'utilisateur te le demande, initie l'environnement de développement, aide-le à choisir entre Python et Node.js, configure la route webhook et pose les bases du mécanisme d'auto-correction.
