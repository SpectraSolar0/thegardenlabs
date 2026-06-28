# Configuration — Comptes, emails & admin

## 1. Variables d'environnement à configurer sur Render

Va dans ton service Render → **Environment** → ajoute ces variables :

| Variable         | Exemple                          | Description                                                                 |
|------------------|-----------------------------------|-------------------------------------------------------------------------------|
| `SECRET_KEY`     | une longue chaîne aléatoire       | Sécurise les sessions. Génère-en une avec `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_EMAIL`    | `toi@tonemail.com`                | L'email qui deviendra automatiquement administrateur à l'inscription         |
| `SITE_URL`       | `https://tonsite.onrender.com`    | URL publique de ton site (utilisée dans les liens des emails)                |
| `SMTP_USER`      | `toncompte@gmail.com`             | Ton adresse Gmail complète                                                   |
| `SMTP_PASSWORD`  | `xxxx xxxx xxxx xxxx`             | **Mot de passe d'application** Gmail (PAS ton mot de passe normal, voir ci-dessous) |
| `SMTP_FROM_NAME` | `TheGarden Labs`                  | Nom affiché comme expéditeur (optionnel, valeur par défaut déjà correcte)    |

Si `SMTP_USER` / `SMTP_PASSWORD` ne sont pas configurés, le site fonctionne quand même,
mais les emails ne sont pas envoyés (seulement affichés dans les logs Render). Pratique
pour tester avant de configurer Gmail.

## 2. Créer un mot de passe d'application Gmail

Gmail bloque les connexions SMTP avec ton mot de passe normal. Il faut un
"mot de passe d'application" dédié :

1. Active la **validation en deux étapes** sur ton compte Google (obligatoire), via
   https://myaccount.google.com/security
2. Va sur https://myaccount.google.com/apppasswords
3. Crée un mot de passe d'application (nom libre, ex : "TheGarden Labs")
4. Google te donne un code à 16 caractères (ex : `abcd efgh ijkl mnop`)
5. Mets ce code dans la variable `SMTP_PASSWORD` sur Render (les espaces n'ont pas
   d'importance, tu peux les garder ou les enlever)
6. Mets ton adresse Gmail complète dans `SMTP_USER`

Limite Gmail gratuite : environ 500 emails/jour, largement suffisant pour démarrer.

## 3. Devenir administrateur

1. Mets ton email perso dans `ADMIN_EMAIL` sur Render (avant ou après le déploiement)
2. Va sur le site et crée un compte normal avec **exactement cet email**
3. Vérifie ton email comme n'importe quel utilisateur (lien reçu par email)
4. Connecte-toi : tu seras automatiquement redirigé vers `/admin` au lieu de `/account`

Si tu changes `ADMIN_EMAIL` plus tard pour promouvoir quelqu'un d'autre, son compte
sera promu admin automatiquement au prochain redémarrage du serveur (la fonction
`ensure_admin_account()` tourne à chaque démarrage). Tu peux aussi promouvoir/rétrograder
n'importe qui directement depuis `/admin/users` une fois connecté en admin.

## 4. Ce qui a changé par rapport à l'ancienne version

- Les commandes et tickets nécessitent maintenant un compte connecté et vérifié.
- Chaque commande/ticket est lié à un `user_id`.
- Le client a un espace "Mon compte" (`/account`) avec l'historique de ses
  commandes et tickets, et peut échanger des messages directement avec l'admin
  sur chaque commande/ticket (fil de discussion).
- L'admin a un espace complet (`/admin`) avec statistiques, gestion des commandes,
  des tickets (réponse + changement de statut), et gestion des utilisateurs
  (promouvoir/rétrograder en admin).
- Toute réponse (client → admin ou admin → client) envoie une notification email
  en plus d'être visible directement sur le site.

## 5. Base de données

⚠️ Les anciennes commandes/tickets (créés avant cette mise à jour, sans `user_id`)
ne seront plus visibles, car les nouvelles requêtes filtrent par compte. Si tu as des
données existantes importantes dans `data/orders.db`, dis-le-moi et je peux écrire un
script de migration qui les rattache à des comptes (ou les garde visibles côté admin
même sans `user_id`).

Si la base est encore vide ou pas critique, le plus simple est de supprimer l'ancien
fichier `data/orders.db` avant le premier déploiement de cette version — il sera
recréé automatiquement avec les nouvelles tables.
