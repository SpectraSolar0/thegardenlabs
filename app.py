from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "thegarden-labs-secret-2024"

DB_PATH = "data/orders.db"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            discord TEXT,
            product TEXT NOT NULL,
            product_price TEXT NOT NULL,
            message TEXT,
            accepted_cgv INTEGER NOT NULL DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ---------------------------------------------------------------------------
# Products config — MODIFIABLE FACILEMENT
# ---------------------------------------------------------------------------

PRODUCTS = {
    "server-pack": {
        "id": "server-pack",
        "category": "Serveur Discord",
        "name": "Pack Serveur Unique",
        "tagline": "Votre serveur Discord, clé en main.",
        "price": "5€",
        "price_raw": "5",
        "type": "one-time",
        "icon": "🌐",
        "badge": None,
        "features": [
            "Création complète des salons textuels & vocaux",
            "Configuration des rôles sur mesure",
            "Permissions sécurisées et hiérarchisées",
            "Intégration de bots essentiels",
            "Livraison sous 24h",
        ],
        "cta": "Commander maintenant",
    },
    "bot-prefait": {
        "id": "bot-prefait",
        "category": "Bot Discord",
        "name": "Bot Préfait",
        "tagline": "Opérationnel en quelques minutes.",
        "price": "1€/mois",
        "price_raw": "1",
        "type": "monthly",
        "icon": "👔",
        "badge": "Populaire",
        "features": [
            "Bot prêt à l'emploi, déployé immédiatement",
            "Installation sur votre serveur incluse",
            "Maintenance & mises à jour comprises",
            "Premier mois offert",
            "Support Discord prioritaire",
        ],
        "cta": "Démarrer — 1er mois gratuit",
    },
    "bot-custom": {
        "id": "bot-custom",
        "category": "Bot Discord",
        "name": "Bot Personnalisé",
        "tagline": "Un bot unique, pensé pour vous.",
        "price": "5€",
        "price_raw": "5",
        "type": "one-time + hosting",
        "icon": "⚙️",
        "badge": "Sur mesure",
        "features": [
            "Développement 100% sur mesure",
            "Nom & branding personnalisés",
            "Commandes et fonctionnalités spécifiques",
            "Premier mois d'hébergement offert",
            "Hébergement ensuite selon ressources (CPU / DB / usage)",
        ],
        "cta": "Demander un devis",
    },
}

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", products=PRODUCTS)

@app.route("/marketplace")
def marketplace():
    return render_template("marketplace.html", products=PRODUCTS)

@app.route("/product/<product_id>")
def product(product_id):
    p = PRODUCTS.get(product_id)
    if not p:
        return redirect(url_for("marketplace"))
    return render_template("product.html", product=p, products=PRODUCTS)

@app.route("/checkout/<product_id>", methods=["GET", "POST"])
def checkout(product_id):
    p = PRODUCTS.get(product_id)
    if not p:
        return redirect(url_for("marketplace"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        discord = request.form.get("discord", "").strip()
        message = request.form.get("message", "").strip()
        accepted_cgv = request.form.get("cgv") == "on"

        errors = []
        if not name:
            errors.append("Le nom est requis.")
        if not email or "@" not in email:
            errors.append("Une adresse email valide est requise.")
        if not accepted_cgv:
            errors.append("Vous devez accepter les Conditions de Vente pour continuer.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("checkout.html", product=p, form=request.form)

        conn = get_db()
        conn.execute(
            """INSERT INTO orders (name, email, discord, product, product_price, message, accepted_cgv, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, email, discord, p["name"], p["price"], message, 1, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

        return redirect(url_for("success", product_id=product_id))

    return render_template("checkout.html", product=p, form={})

@app.route("/success/<product_id>")
def success(product_id):
    p = PRODUCTS.get(product_id)
    return render_template("success.html", product=p)

@app.route("/cgv")
def cgv():
    return render_template("cgv.html")

@app.route("/admin/orders")
def admin_orders():
    conn = get_db()
    orders = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("admin_orders.html", orders=orders)

# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
