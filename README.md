# 🌸 TheGarden Labs

Site web premium pour la vente de serveurs et bots Discord.

---

## 🚀 Lancement rapide

### 1. Installer Python 3.10+
https://python.org

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 3. Lancer le serveur

```bash
python app.py
```

### 4. Ouvrir dans le navigateur

```
http://localhost:5000
```

---

## 📁 Structure du projet

```
thegarden-labs/
├── app.py                  # App principale Flask (routes + config)
├── requirements.txt
├── data/
│   └── orders.db           # Base SQLite (créée automatiquement)
├── static/
│   ├── css/main.css        # Design system complet
│   ├── js/main.js          # Interactions légères
│   └── images/
│       └── logo.png        # Logo TheGarden Labs
└── templates/
    ├── base.html           # Layout commun (nav + footer)
    ├── index.html          # Landing page
    ├── marketplace.html    # Page catalogue
    ├── product.html        # Page produit individuel
    ├── checkout.html       # Page commande (avec CGV obligatoires)
    ├── success.html        # Confirmation commande
    ├── cgv.html            # Conditions Générales de Vente
    └── admin_orders.html   # Vue admin des commandes
```

---

## 🔧 Personnalisation facile

### Modifier les produits / prix
Ouvrez `app.py` et éditez le dictionnaire `PRODUCTS` (ligne ~25).
Chaque produit a : name, price, features, icon, cta...

### Modifier les textes du site
Chaque page est un template HTML dans `/templates/`. Le texte est directement éditable.

### Changer le lien Discord
Recherchez `https://discord.gg/` dans les templates et remplacez par votre vrai lien d'invitation.

---

## 👤 Admin

Pour voir les commandes reçues :
```
http://localhost:5000/admin/orders
```

---

## 🌐 Déploiement gratuit (optionnel)

### Option 1 — Render.com (recommandé)
1. Créez un compte sur https://render.com
2. "New Web Service" → connectez votre repo GitHub
3. Build command : `pip install -r requirements.txt`
4. Start command : `gunicorn app:app`
5. Ajoutez `gunicorn` dans requirements.txt

### Option 2 — Railway.app
1. Créez un compte sur https://railway.app
2. "Deploy from GitHub repo"
3. Railway détecte Flask automatiquement

### Option 3 — PythonAnywhere (gratuit)
1. Compte gratuit sur https://pythonanywhere.com
2. Upload les fichiers, configurez le WSGI

---

## 📝 Notes techniques

- Base de données : SQLite (`data/orders.db`) — créée automatiquement au premier lancement
- Aucune dépendance externe sauf Flask
- Design system : CSS variables, responsive mobile-first
- Animations : IntersectionObserver (fade-up léger), pas de librairie JS
