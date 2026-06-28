# Configuration — Comptes, emails & admin

## ⚠️ Important : pourquoi Resend et pas Gmail SMTP

Render bloque les connexions SMTP sortantes (port 587 vers Gmail) sur la plupart des
offres — c'est une protection anti-spam courante chez les hébergeurs cloud. Du coup
Gmail SMTP ne fonctionnera jamais correctement sur Render, peu importe la config.

**Resend** envoie les emails via une API HTTPS classique (comme n'importe quel appel
réseau normal), donc ça passe sans problème sur Render. Gratuit jusqu'à 3000 emails/mois.

## 1. Créer un compte Resend et récupérer une clé API

1. Va sur https://resend.com et crée un compte (gratuit)
2. Dans le dashboard, va dans **API Keys** → **Create API Key**
3. Donne-lui un nom (ex: "thegardenlabs-prod") et copie la clé (commence par `re_...`)
   ⚠️ Elle ne sera affichée qu'une seule fois, donc copie-la tout de suite

## 2. Vérifier ton nom de domaine sur Resend (obligatoire pour envoyer à n'importe qui)

Sans domaine vérifié, Resend ne permet d'envoyer qu'à l'adresse email du compte qui a
créé la clé API (utile pour tester, mais pas pour de vrais clients). Comme tu as un
nom de domaine, autant le vérifier dès maintenant :

1. Dans le dashboard Resend, va dans **Domains** → **Add Domain**
2. Entre ton nom de domaine (ex: `thegardenlabs.com`)
3. Resend te donne 2-3 enregistrements DNS à ajouter (des `TXT` et un `MX` ou `CNAME`
   selon la config) chez ton registrar (OVH, Namecheap, etc.)
4. Ajoute ces enregistrements dans la zone DNS de ton domaine
5. Reviens sur Resend et clique sur **Verify** — ça peut prendre de quelques minutes
   à quelques heures selon la propagation DNS
6. Une fois vérifié, tu peux envoyer depuis n'importe quelle adresse `@tondomaine.com`,
   par exemple `noreply@thegardenlabs.com`

## 3. Variables d'environnement à configurer sur Render

Va dans ton service Render → **Environment** → ajoute ces variables :

| Variable             | Exemple                          | Description                                                                 |
|-----------------------|-----------------------------------|-------------------------------------------------------------------------------|
| `SECRET_KEY`          | une longue chaîne aléatoire       | Sécurise les sessions. Génère-en une avec `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `ADMIN_EMAIL`         | `toi@tonemail.com`                | L'email qui deviendra automatiquement administrateur à l'inscription         |
| `SITE_URL`            | `https://tonsite.onrender.com`    | URL publique de ton site (utilisée dans les liens des emails)                |
| `RESEND_API_KEY`      | `re_xxxxxxxxxxxxxxxxxxxx`         | Ta clé API Resend (étape 1)                                                   |
| `RESEND_FROM_EMAIL`   | `noreply@thegardenlabs.com`       | Adresse d'envoi, doit être sur un domaine vérifié sur Resend (étape 2)        |
| `RESEND_FROM_NAME`    | `TheGarden Labs`                  | Nom affiché comme expéditeur (optionnel, valeur par défaut déjà correcte)    |

Si `RESEND_API_KEY` / `RESEND_FROM_EMAIL` ne sont pas configurés, le site fonctionne
quand même : les emails ne sont pas envoyés, mais l'inscription et tout le reste
continuent de marcher normalement (le contenu de l'email est juste affiché dans les
logs Render). Pratique pour tester avant de tout configurer.


## 4. Devenir administrateur

1. Mets ton email perso dans `ADMIN_EMAIL` sur Render (avant ou après le déploiement)
2. Va sur le site et crée un compte normal avec **exactement cet email**
3. Vérifie ton email comme n'importe quel utilisateur (lien reçu par email)
4. Connecte-toi : tu seras automatiquement redirigé vers `/admin` au lieu de `/account`

Si tu changes `ADMIN_EMAIL` plus tard pour promouvoir quelqu'un d'autre, son compte
sera promu admin automatiquement au prochain redémarrage du serveur (la fonction
`ensure_admin_account()` tourne à chaque démarrage). Tu peux aussi promouvoir/rétrograder
n'importe qui directement depuis `/admin/users` une fois connecté en admin.

## 5. Ce qui a changé par rapport à l'ancienne version

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

## 6. Base de données

⚠️ Les anciennes commandes/tickets (créés avant cette mise à jour, sans `user_id`)
ne seront plus visibles, car les nouvelles requêtes filtrent par compte. Si tu as des
données existantes importantes dans `data/orders.db`, dis-le-moi et je peux écrire un
script de migration qui les rattache à des comptes (ou les garde visibles côté admin
même sans `user_id`).

Si la base est encore vide ou pas critique, le plus simple est de supprimer l'ancien
fichier `data/orders.db` avant le premier déploiement de cette version — il sera
recréé automatiquement avec les nouvelles tables.
