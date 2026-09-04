# 🔎 Workflow : Auto-Vérification (Self-Check)

> Chaque réponse générée par l'agent est évaluée AVANT d'être envoyée au client.
> Inspiré du pattern Self-Verification (cf. Obsidian: Auto-Vérification.md)
> Utilise un modèle rapide et pas cher (Haiku) pour la vérification.

---

## 🎯 Objectif
Empêcher l'envoi de réponses incorrectes, inappropriées ou dangereuses
au client. C'est le "filet de sécurité" du bot.

---

## 📋 Grille d'Évaluation

L'évaluateur vérifie chaque réponse sur 5 critères. Chaque critère est
PASS ou FAIL. Un seul FAIL → la réponse est rejetée.

### 1. Factualité (HALLUCINATION CHECK)
- La réponse contient-elle des informations factuelles sur la boutique (prix, modèles, politiques de retour, livraison) qui NE SONT PAS dans `knowledge.md` ?
- Invente-t-elle des délais, des prix ou des politiques non documentés ?
- Promet-elle une action que le système ne peut pas effectuer ?
- NOTE : Saluer le client par son prénom (fourni dans le contexte) ou répondre chaleureusement à un remerciement / compliment ("Merci !", "Avec plaisir", etc.) fait partie de la politesse normale et N'EST PAS une hallucination.
→ FAIL uniquement si fausse information sur la boutique/services → Label : `failed_hallucination`

### 2. Ton et Empathie (TONE CHECK)
- Le ton est-il empathique et professionnel ?
- Y a-t-il des formulations froides, robotiques ou agressives ?
- Le message reconnaît-il l'émotion du client si nécessaire ?
→ FAIL si ton inapproprié → Label : `failed_tone`

### 3. Langue (LANGUAGE CHECK)
- La réponse est-elle dans la même langue que le message du client ?
- Y a-t-il un mélange involontaire de langues ?
→ FAIL si mauvaise langue → Label : `failed_language`

### 4. Périmètre (SCOPE CHECK)
- La réponse traite-t-elle d'un sujet couvert par `knowledge.md` ?
- Le bot répond-il à des questions qui devraient être escaladées ?
→ FAIL si hors périmètre → Label : `failed_out_of_scope`

### 5. Nécessité d'Escalade (ESCALATION CHECK)
- La question nécessite-t-elle une intervention humaine ?
- Le bot tente-t-il de résoudre seul un cas qu'il devrait escalader ?
→ FAIL si escalade nécessaire → Label : `needs_escalation`

---

## 🔄 Actions selon le Résultat

| Résultat | Action |
|----------|--------|
| 5/5 PASS | ✅ Envoyer la réponse au client |
| FAIL tone/language | 🔄 Régénérer la réponse (max 2 retries) |
| FAIL hallucination | 🔄 Régénérer avec instruction stricte "utiliser UNIQUEMENT knowledge.md" |
| FAIL scope/escalation | 🚨 Déclencher le workflow d'escalade |

---

## 💰 Optimisation des Coûts (Routage de Modèles)
- Le Self-Check utilise un **modèle rapide et pas cher** (Haiku, GPT-4o-mini)
- Le coût additionnel est minimal (~0.001$ par vérification)
- Le gain en fiabilité est immense (éviter 1 hallucination = éviter 1 client perdu)
