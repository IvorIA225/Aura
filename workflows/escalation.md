# 🚨 Workflow : Escalade Humaine (HITL)

> Déclenché quand l'agent ne peut ou ne doit pas répondre seul.
> Inspiré du pattern Human-in-the-Loop (cf. Obsidian: Humain_dans_la_Boucle.md)

---

## 🎯 Objectif
Transférer la conversation à un humain de manière fluide, en fournissant
tout le contexte nécessaire pour que l'humain puisse reprendre sans friction.

---

## 🔴 Déclencheurs d'Escalade

### Escalade OBLIGATOIRE (actions interdites au bot)
- Demande de remboursement
- Demande d'annulation de commande
- Modification d'informations de paiement
- Double débit signalé
- Menace légale ou demande juridique

### Escalade RECOMMANDÉE (incertitude)
- Question à laquelle la knowledge base ne répond pas
- Client visiblement très mécontent (insultes, majuscules, urgence répétée)
- Conversation qui tourne en boucle (>3 échanges sans résolution)
- Demande complexe impliquant plusieurs systèmes

### Escalade OPTIONNELLE (amélioration)
- Suggestion produit ou feedback constructif du client
- Demande de fonctionnalité

---

## 🔄 Étapes de l'Escalade

### 1. Informer le Client
Envoyer un message empathique expliquant le transfert :
- "Je vais transmettre votre demande à notre équipe spécialisée."
- "Un conseiller va prendre en charge votre dossier."
- "Vous recevrez une réponse sous 24h ouvrées."

### 2. Créer le Ticket Notion
Créer une page dans la base Notion "Tickets Support" avec :
- **Titre** : Résumé de la demande en 1 phrase
- **Client** : Nom + numéro WhatsApp
- **Priorité** :
  - 🔴 Urgent : double débit, menace légale
  - 🟠 Haute : remboursement, client très mécontent
  - 🟡 Moyenne : annulation, modification commande
  - 🟢 Basse : question, feedback
- **Contexte** : Les 5 derniers messages de la conversation
- **Raison de l'escalade** : Pourquoi le bot ne peut pas résoudre
- **Statut** : "Nouveau"

### 3. Notifier l'Équipe
- Envoyer un email/Slack avec le lien du ticket Notion
- Inclure un résumé de la situation en 2 lignes

### 4. Loguer l'Escalade
- Enregistrer l'action dans la table `agent_logs` (Supabase)
- Mettre le statut de la conversation à "escalated"

---

## ⚠️ Ce que le bot NE DOIT PAS faire pendant l'escalade
- Ne PAS promettre un résultat spécifique ("Vous serez remboursé")
- Ne PAS donner de délai précis ("Vous aurez une réponse dans 2h")
- Ne PAS dire "Je ne peux pas vous aider" → Toujours reformuler positivement

---

## 🔗 Workflows Liés
- `whatsapp_support.md` : Workflow parent qui déclenche l'escalade
