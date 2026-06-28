from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
import sqlite3
import os
import secrets
import requests
from datetime import datetime, timedelta
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "thegarden-labs-secret-2024")

DB_PATH = "data/orders.db"

# ---------------------------------------------------------------------------
# Config — à modifier ici uniquement
# ---------------------------------------------------------------------------

DISCORD_INVITE = "https://discord.gg/PAZHhUSXZj"  # <-- change ton lien d'invitation ici

# Email de l'admin : le compte créé avec cet email devient automatiquement admin
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")

# URL de base du site, utilisée dans les emails (liens de vérification, etc.)
SITE_URL = os.environ.get("SITE_URL", "http://localhost:5000")

# Config Resend (API HTTPS — fonctionne sur Render, contrairement à SMTP qui peut être bloqué)
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")  # ta clé API Resend (commence par re_)
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "")  # ex: noreply@tondomaine.com (domaine vérifié sur Resend)
RESEND_FROM_NAME = os.environ.get("RESEND_FROM_NAME", "TheGarden Labs")

EMAIL_ENABLED = bool(RESEND_API_KEY and RESEND_FROM_EMAIL)


@app.context_processor
def inject_globals():
    # Rend ces variables disponibles dans TOUS les templates automatiquement
    return {
        "discord_invite": DISCORD_INVITE,
        "current_user": get_current_user(),
    }

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            discord TEXT,
            is_admin INTEGER NOT NULL DEFAULT 0,
            is_verified INTEGER NOT NULL DEFAULT 0,
            verify_token TEXT,
            verify_token_expires TEXT,
            reset_token TEXT,
            reset_token_expires TEXT,
            created_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            discord TEXT,
            product TEXT NOT NULL,
            product_price TEXT NOT NULL,
            message TEXT,
            accepted_cgv INTEGER NOT NULL DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            discord TEXT,
            subject TEXT NOT NULL,
            category TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    # Fil de discussion pour les tickets (réponses client <-> admin)
    c.execute("""
        CREATE TABLE IF NOT EXISTS ticket_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            is_admin_reply INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (ticket_id) REFERENCES tickets (id),
            FOREIGN KEY (author_id) REFERENCES users (id)
        )
    """)

    # Fil de discussion pour les commandes (réponses client <-> admin)
    c.execute("""
        CREATE TABLE IF NOT EXISTS order_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            is_admin_reply INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (id),
            FOREIGN KEY (author_id) REFERENCES users (id)
        )
    """)

    conn.commit()

    # Migration douce : si d'anciennes tables orders/tickets existaient sans user_id,
    # SQLite ne permet pas d'ALTER facilement avec contrainte NOT NULL, donc on vérifie juste
    # que les colonnes existent (pour les bases déjà migrées par une version précédente).
    conn.close()


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_admin_account():
    """S'assure qu'un compte admin existe pour ADMIN_EMAIL.
    Si le compte existe déjà (créé via inscription normale), il est promu admin.
    Sinon, rien n'est créé automatiquement : la personne doit s'inscrire avec cet email,
    et elle sera automatiquement promue admin + vérifiée à l'inscription."""
    conn = get_db()
    conn.execute(
        "UPDATE users SET is_admin = 1, is_verified = 1 WHERE email = ?",
        (ADMIN_EMAIL,),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def get_current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return user


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not get_current_user():
            flash("Merci de te connecter pour accéder à cette page.", "error")
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            flash("Merci de te connecter pour accéder à cette page.", "error")
            return redirect(url_for("login", next=request.path))
        if not user["is_admin"]:
            flash("Accès réservé aux administrateurs.", "error")
            return redirect(url_for("index"))
        return f(*args, **kwargs)
    return decorated


def make_token():
    return secrets.token_urlsafe(32)


# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------

def send_email(to_email, subject, html_body):
    """Envoie un email via l'API Resend (HTTPS, pas bloqué par les hébergeurs comme SMTP peut l'être).
    Si Resend n'est pas configuré, le contenu est simplement affiché dans les logs (utile en dev local).
    Le timeout est volontairement court : un problème réseau ne doit jamais faire planter la requête
    en cours (inscription, réponse à un ticket, etc.) — l'email est "best effort"."""
    if not EMAIL_ENABLED:
        print(f"--- [EMAIL NON ENVOYÉ — Resend non configuré] ---")
        print(f"À: {to_email}\nSujet: {subject}\n{html_body}")
        print("--- Configure RESEND_API_KEY et RESEND_FROM_EMAIL pour activer l'envoi réel ---")
        return False

    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "from": f"{RESEND_FROM_NAME} <{RESEND_FROM_EMAIL}>",
                "to": [to_email],
                "subject": subject,
                "html": html_body,
            },
            timeout=8,  # court et volontaire : on ne bloque jamais longtemps une requête utilisateur
        )
        if response.status_code >= 400:
            print(f"Erreur Resend ({response.status_code}) pour {to_email}: {response.text}")
            return False
        return True
    except requests.exceptions.RequestException as e:
        print(f"Erreur d'envoi d'email (réseau) à {to_email}: {e}")
        return False


def send_verification_email(user_email, token):
    link = f"{SITE_URL}{url_for('verify_email', token=token)}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;">
        <h2>Bienvenue sur TheGarden Labs 🌱</h2>
        <p>Merci de confirmer ton adresse email pour activer ton compte :</p>
        <p><a href="{link}" style="background:#5865F2;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;display:inline-block;">Confirmer mon email</a></p>
        <p>Ou copie ce lien : {link}</p>
        <p style="color:#888;font-size:0.85em;">Ce lien expire dans 24h.</p>
    </div>
    """
    send_email(user_email, "Confirme ton compte — TheGarden Labs", html)


def send_reset_email(user_email, token):
    link = f"{SITE_URL}{url_for('reset_password', token=token)}"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;">
        <h2>Réinitialisation du mot de passe</h2>
        <p>Clique sur le lien ci-dessous pour choisir un nouveau mot de passe :</p>
        <p><a href="{link}" style="background:#5865F2;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;display:inline-block;">Réinitialiser mon mot de passe</a></p>
        <p>Ou copie ce lien : {link}</p>
        <p style="color:#888;font-size:0.85em;">Si tu n'as pas demandé ça, ignore simplement cet email. Ce lien expire dans 1h.</p>
    </div>
    """
    send_email(user_email, "Réinitialisation du mot de passe — TheGarden Labs", html)


def send_new_reply_notification_to_client(user_email, kind, ref_id, subject_text):
    """kind = 'ticket' ou 'order'"""
    if kind == "ticket":
        link = f"{SITE_URL}{url_for('my_ticket', ticket_id=ref_id)}"
        label = "ticket"
    else:
        link = f"{SITE_URL}{url_for('my_order', order_id=ref_id)}"
        label = "commande"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;">
        <h2>Nouvelle réponse à ton {label}</h2>
        <p>Un administrateur a répondu à ton {label} concernant : <strong>{subject_text}</strong></p>
        <p><a href="{link}" style="background:#5865F2;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;display:inline-block;">Voir la réponse</a></p>
    </div>
    """
    send_email(user_email, f"Nouvelle réponse à ton {label} — TheGarden Labs", html)


def send_new_message_notification_to_admins(kind, ref_id, subject_text, from_email):
    """Notifie l'admin (ADMIN_EMAIL) qu'un client a écrit / répondu."""
    if kind == "ticket":
        link = f"{SITE_URL}{url_for('admin_ticket_detail', ticket_id=ref_id)}"
        label = "ticket"
    else:
        link = f"{SITE_URL}{url_for('admin_order_detail', order_id=ref_id)}"
        label = "commande"
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:0 auto;">
        <h2>Nouveau message sur un {label}</h2>
        <p>{from_email} a écrit sur le {label} : <strong>{subject_text}</strong></p>
        <p><a href="{link}" style="background:#5865F2;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;display:inline-block;">Voir et répondre</a></p>
    </div>
    """
    send_email(ADMIN_EMAIL, f"Nouveau message — {label} #{ref_id}", html)


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

TICKET_CATEGORIES = [
    "Question avant achat",
    "Suivi de commande",
    "Problème technique / bot",
    "Facturation",
    "Autre",
]

# ---------------------------------------------------------------------------
# Routes — Site
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

# ---------------------------------------------------------------------------
# Routes — Auth (inscription, vérification, connexion, déconnexion, reset)
# ---------------------------------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if get_current_user():
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")
        discord = request.form.get("discord", "").strip()

        errors = []
        if not email or "@" not in email:
            errors.append("Une adresse email valide est requise.")
        if len(password) < 8:
            errors.append("Le mot de passe doit contenir au moins 8 caractères.")
        if password != password2:
            errors.append("Les mots de passe ne correspondent pas.")

        if not errors:
            conn = get_db()
            existing = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
            if existing:
                errors.append("Un compte existe déjà avec cet email.")
            conn.close()

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("register.html", form=request.form)

        is_admin_account = 1 if email == ADMIN_EMAIL.lower() else 0
        token = make_token()
        expires = (datetime.now() + timedelta(hours=24)).isoformat()

        conn = get_db()
        conn.execute(
            """INSERT INTO users (email, password_hash, discord, is_admin, is_verified, verify_token, verify_token_expires, created_at)
               VALUES (?, ?, ?, ?, 0, ?, ?, ?)""",
            (email, generate_password_hash(password), discord, is_admin_account, token, expires, datetime.now().isoformat()),
        )
        conn.commit()
        conn.close()

        send_verification_email(email, token)

        flash("Compte créé ! Vérifie ta boîte mail pour confirmer ton adresse avant de te connecter.", "success")
        return redirect(url_for("login"))

    return render_template("register.html", form={})


@app.route("/verify/<token>")
def verify_email(token):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE verify_token = ?", (token,)).fetchone()

    if not user:
        conn.close()
        flash("Lien de vérification invalide ou déjà utilisé.", "error")
        return redirect(url_for("login"))

    if user["verify_token_expires"] and datetime.now() > datetime.fromisoformat(user["verify_token_expires"]):
        conn.close()
        flash("Ce lien de vérification a expiré. Demande un nouvel email depuis la page de connexion.", "error")
        return redirect(url_for("login"))

    conn.execute(
        "UPDATE users SET is_verified = 1, verify_token = NULL, verify_token_expires = NULL WHERE id = ?",
        (user["id"],),
    )
    conn.commit()
    conn.close()

    flash("Email confirmé avec succès ! Tu peux maintenant te connecter.", "success")
    return redirect(url_for("login"))


@app.route("/resend-verification", methods=["POST"])
def resend_verification():
    email = request.form.get("email", "").strip().lower()
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

    if user and not user["is_verified"]:
        token = make_token()
        expires = (datetime.now() + timedelta(hours=24)).isoformat()
        conn.execute(
            "UPDATE users SET verify_token = ?, verify_token_expires = ? WHERE id = ?",
            (token, expires, user["id"]),
        )
        conn.commit()
        send_verification_email(email, token)

    conn.close()
    # Message volontairement neutre, qu'un compte existe ou non (évite de révéler les emails enregistrés)
    flash("Si ce compte existe et n'est pas encore vérifié, un nouvel email vient d'être envoyé.", "success")
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Email ou mot de passe incorrect.", "error")
            return render_template("login.html", form=request.form)

        if not user["is_verified"]:
            flash("Merci de confirmer ton email avant de te connecter (vérifie ta boîte mail).", "error")
            return render_template("login.html", form=request.form, unverified_email=email)

        session["user_id"] = user["id"]
        flash(f"Bienvenue, {email} !", "success")

        next_url = request.args.get("next")
        if next_url:
            return redirect(next_url)
        return redirect(url_for("admin_dashboard") if user["is_admin"] else url_for("dashboard"))

    return render_template("login.html", form={})


@app.route("/logout")
def logout():
    session.clear()
    flash("Tu as été déconnecté.", "success")
    return redirect(url_for("index"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if user:
            token = make_token()
            expires = (datetime.now() + timedelta(hours=1)).isoformat()
            conn.execute(
                "UPDATE users SET reset_token = ?, reset_token_expires = ? WHERE id = ?",
                (token, expires, user["id"]),
            )
            conn.commit()
            send_reset_email(email, token)

        conn.close()
        flash("Si ce compte existe, un email de réinitialisation vient d'être envoyé.", "success")
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE reset_token = ?", (token,)).fetchone()

    if not user or (user["reset_token_expires"] and datetime.now() > datetime.fromisoformat(user["reset_token_expires"])):
        conn.close()
        flash("Lien de réinitialisation invalide ou expiré.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        if len(password) < 8:
            flash("Le mot de passe doit contenir au moins 8 caractères.", "error")
            conn.close()
            return render_template("reset_password.html", token=token)
        if password != password2:
            flash("Les mots de passe ne correspondent pas.", "error")
            conn.close()
            return render_template("reset_password.html", token=token)

        conn.execute(
            "UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expires = NULL WHERE id = ?",
            (generate_password_hash(password), user["id"]),
        )
        conn.commit()
        conn.close()

        flash("Mot de passe mis à jour. Tu peux te connecter.", "success")
        return redirect(url_for("login"))

    conn.close()
    return render_template("reset_password.html", token=token)


# ---------------------------------------------------------------------------
# Routes — Checkout (commandes) — nécessite un compte
# ---------------------------------------------------------------------------

@app.route("/checkout/<product_id>", methods=["GET", "POST"])
@login_required
def checkout(product_id):
    p = PRODUCTS.get(product_id)
    if not p:
        return redirect(url_for("marketplace"))

    user = get_current_user()

    if request.method == "POST":
        discord = request.form.get("discord", "").strip()
        message = request.form.get("message", "").strip()
        accepted_cgv = request.form.get("cgv") == "on"

        errors = []
        if not accepted_cgv:
            errors.append("Vous devez accepter les Conditions de Vente pour continuer.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("checkout.html", product=p, form=request.form)

        conn = get_db()
        cur = conn.execute(
            """INSERT INTO orders (user_id, name, email, discord, product, product_price, message, accepted_cgv, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (user["id"], user["email"].split("@")[0], user["email"], discord or user["discord"], p["name"], p["price"], message, 1, datetime.now().isoformat()),
        )
        order_id = cur.lastrowid
        conn.commit()
        conn.close()

        send_new_message_notification_to_admins("order", order_id, p["name"], user["email"])

        return redirect(url_for("success", product_id=product_id))

    return render_template("checkout.html", product=p, form={"discord": user["discord"] or ""})

@app.route("/success/<product_id>")
@login_required
def success(product_id):
    p = PRODUCTS.get(product_id)
    return render_template("success.html", product=p)

@app.route("/cgv")
def cgv():
    return render_template("cgv.html")

# ---------------------------------------------------------------------------
# Routes — Système de tickets — nécessite un compte
# ---------------------------------------------------------------------------

@app.route("/support", methods=["GET", "POST"])
@login_required
def support():
    user = get_current_user()

    if request.method == "POST":
        discord = request.form.get("discord", "").strip()
        category = request.form.get("category", "").strip()
        subject = request.form.get("subject", "").strip()
        message = request.form.get("message", "").strip()

        errors = []
        if category not in TICKET_CATEGORIES:
            errors.append("Merci de choisir une catégorie valide.")
        if not subject:
            errors.append("Le sujet est requis.")
        if not message:
            errors.append("Le message est requis.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("support.html", form=request.form, categories=TICKET_CATEGORIES)

        conn = get_db()
        cur = conn.execute(
            """INSERT INTO tickets (user_id, name, email, discord, subject, category, message, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (user["id"], user["email"].split("@")[0], user["email"], discord or user["discord"], subject, category, message, datetime.now().isoformat()),
        )
        ticket_id = cur.lastrowid
        conn.commit()
        conn.close()

        send_new_message_notification_to_admins("ticket", ticket_id, subject, user["email"])

        return redirect(url_for("support_success", ticket_id=ticket_id))

    return render_template("support.html", form={"discord": user["discord"] or ""}, categories=TICKET_CATEGORIES)

@app.route("/support/success/<int:ticket_id>")
@login_required
def support_success(ticket_id):
    conn = get_db()
    ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    conn.close()
    if not ticket:
        return redirect(url_for("support"))
    return render_template("support_success.html", ticket=ticket)


# ---------------------------------------------------------------------------
# Routes — Espace client ("Mon compte")
# ---------------------------------------------------------------------------

@app.route("/account")
@login_required
def dashboard():
    user = get_current_user()
    conn = get_db()
    orders = conn.execute(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)
    ).fetchall()
    tickets = conn.execute(
        "SELECT * FROM tickets WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)
    ).fetchall()
    conn.close()
    return render_template("dashboard.html", orders=orders, tickets=tickets)


@app.route("/account/orders/<int:order_id>", methods=["GET", "POST"])
@login_required
def my_order(order_id):
    user = get_current_user()
    conn = get_db()
    order = conn.execute(
        "SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user["id"])
    ).fetchone()

    if not order:
        conn.close()
        flash("Commande introuvable.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        message = request.form.get("message", "").strip()
        if message:
            conn.execute(
                """INSERT INTO order_messages (order_id, author_id, is_admin_reply, message, created_at)
                   VALUES (?, ?, 0, ?, ?)""",
                (order_id, user["id"], message, datetime.now().isoformat()),
            )
            conn.commit()
            send_new_message_notification_to_admins("order", order_id, order["product"], user["email"])

    messages = conn.execute(
        """SELECT order_messages.*, users.email as author_email
           FROM order_messages JOIN users ON order_messages.author_id = users.id
           WHERE order_id = ? ORDER BY created_at ASC""",
        (order_id,),
    ).fetchall()
    conn.close()

    return render_template("my_order.html", order=order, messages=messages)


@app.route("/account/tickets/<int:ticket_id>", methods=["GET", "POST"])
@login_required
def my_ticket(ticket_id):
    user = get_current_user()
    conn = get_db()
    ticket = conn.execute(
        "SELECT * FROM tickets WHERE id = ? AND user_id = ?", (ticket_id, user["id"])
    ).fetchone()

    if not ticket:
        conn.close()
        flash("Ticket introuvable.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        message = request.form.get("message", "").strip()
        if message:
            conn.execute(
                """INSERT INTO ticket_messages (ticket_id, author_id, is_admin_reply, message, created_at)
                   VALUES (?, ?, 0, ?, ?)""",
                (ticket_id, user["id"], message, datetime.now().isoformat()),
            )
            # Réouverture automatique si le client répond à un ticket fermé
            conn.execute("UPDATE tickets SET status = 'open' WHERE id = ?", (ticket_id,))
            conn.commit()
            send_new_message_notification_to_admins("ticket", ticket_id, ticket["subject"], user["email"])

    messages = conn.execute(
        """SELECT ticket_messages.*, users.email as author_email
           FROM ticket_messages JOIN users ON ticket_messages.author_id = users.id
           WHERE ticket_id = ? ORDER BY created_at ASC""",
        (ticket_id,),
    ).fetchall()
    conn.close()

    return render_template("my_ticket.html", ticket=ticket, messages=messages)


@app.route("/account/settings", methods=["GET", "POST"])
@login_required
def account_settings():
    user = get_current_user()

    if request.method == "POST":
        discord = request.form.get("discord", "").strip()
        new_password = request.form.get("new_password", "")
        new_password2 = request.form.get("new_password2", "")

        conn = get_db()
        conn.execute("UPDATE users SET discord = ? WHERE id = ?", (discord, user["id"]))

        if new_password:
            if len(new_password) < 8:
                flash("Le nouveau mot de passe doit contenir au moins 8 caractères.", "error")
            elif new_password != new_password2:
                flash("Les nouveaux mots de passe ne correspondent pas.", "error")
            else:
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (generate_password_hash(new_password), user["id"]),
                )
                flash("Mot de passe mis à jour.", "success")

        conn.commit()
        conn.close()
        flash("Profil mis à jour.", "success")
        return redirect(url_for("account_settings"))

    return render_template("account_settings.html", user=user)


# ---------------------------------------------------------------------------
# Routes — Admin
# ---------------------------------------------------------------------------

@app.route("/admin")
@admin_required
def admin_dashboard():
    conn = get_db()
    stats = {
        "total_orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "pending_orders": conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'pending'").fetchone()[0],
        "open_tickets": conn.execute("SELECT COUNT(*) FROM tickets WHERE status = 'open'").fetchone()[0],
        "total_users": conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
    }
    recent_orders = conn.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 5").fetchall()
    recent_tickets = conn.execute("SELECT * FROM tickets ORDER BY created_at DESC LIMIT 5").fetchall()
    conn.close()
    return render_template("admin_dashboard.html", stats=stats, recent_orders=recent_orders, recent_tickets=recent_tickets)


@app.route("/admin/orders")
@admin_required
def admin_orders():
    conn = get_db()
    orders = conn.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("admin_orders.html", orders=orders)


@app.route("/admin/orders/<int:order_id>", methods=["GET", "POST"])
@admin_required
def admin_order_detail(order_id):
    conn = get_db()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()

    if not order:
        conn.close()
        flash("Commande introuvable.", "error")
        return redirect(url_for("admin_orders"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "reply":
            message = request.form.get("message", "").strip()
            if message:
                admin = get_current_user()
                conn.execute(
                    """INSERT INTO order_messages (order_id, author_id, is_admin_reply, message, created_at)
                       VALUES (?, ?, 1, ?, ?)""",
                    (order_id, admin["id"], message, datetime.now().isoformat()),
                )
                conn.commit()
                send_new_reply_notification_to_client(order["email"], "order", order_id, order["product"])

        elif action == "status":
            new_status = request.form.get("status")
            if new_status in ("pending", "in_progress", "completed", "cancelled"):
                conn.execute("UPDATE orders SET status = ? WHERE id = ?", (new_status, order_id))
                conn.commit()

    messages = conn.execute(
        """SELECT order_messages.*, users.email as author_email
           FROM order_messages JOIN users ON order_messages.author_id = users.id
           WHERE order_id = ? ORDER BY created_at ASC""",
        (order_id,),
    ).fetchall()
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.close()

    return render_template("admin_order_detail.html", order=order, messages=messages)


@app.route("/admin/tickets")
@admin_required
def admin_tickets():
    conn = get_db()
    tickets = conn.execute("SELECT * FROM tickets ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("admin_tickets.html", tickets=tickets)


@app.route("/admin/tickets/<int:ticket_id>", methods=["GET", "POST"])
@admin_required
def admin_ticket_detail(ticket_id):
    conn = get_db()
    ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()

    if not ticket:
        conn.close()
        flash("Ticket introuvable.", "error")
        return redirect(url_for("admin_tickets"))

    if request.method == "POST":
        action = request.form.get("action")

        if action == "reply":
            message = request.form.get("message", "").strip()
            if message:
                admin = get_current_user()
                conn.execute(
                    """INSERT INTO ticket_messages (ticket_id, author_id, is_admin_reply, message, created_at)
                       VALUES (?, ?, 1, ?, ?)""",
                    (ticket_id, admin["id"], message, datetime.now().isoformat()),
                )
                conn.commit()
                send_new_reply_notification_to_client(ticket["email"], "ticket", ticket_id, ticket["subject"])

        elif action == "toggle_status":
            new_status = "closed" if ticket["status"] == "open" else "open"
            conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (new_status, ticket_id))
            conn.commit()

    messages = conn.execute(
        """SELECT ticket_messages.*, users.email as author_email
           FROM ticket_messages JOIN users ON ticket_messages.author_id = users.id
           WHERE ticket_id = ? ORDER BY created_at ASC""",
        (ticket_id,),
    ).fetchall()
    ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    conn.close()

    return render_template("admin_ticket_detail.html", ticket=ticket, messages=messages)


@app.route("/admin/tickets/<int:ticket_id>/toggle", methods=["POST"])
@admin_required
def admin_ticket_toggle(ticket_id):
    conn = get_db()
    ticket = conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
    if ticket:
        new_status = "closed" if ticket["status"] == "open" else "open"
        conn.execute("UPDATE tickets SET status = ? WHERE id = ?", (new_status, ticket_id))
        conn.commit()
    conn.close()
    return redirect(url_for("admin_tickets"))


@app.route("/admin/users")
@admin_required
def admin_users():
    conn = get_db()
    users = conn.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    conn.close()
    return render_template("admin_users.html", users=users)


@app.route("/admin/users/<int:user_id>/toggle-admin", methods=["POST"])
@admin_required
def admin_toggle_admin(user_id):
    current = get_current_user()
    if current["id"] == user_id:
        flash("Tu ne peux pas modifier ton propre statut admin.", "error")
        return redirect(url_for("admin_users"))

    conn = get_db()
    target = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if target:
        new_value = 0 if target["is_admin"] else 1
        conn.execute("UPDATE users SET is_admin = ? WHERE id = ?", (new_value, user_id))
        conn.commit()
    conn.close()
    return redirect(url_for("admin_users"))


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@admin_required
def admin_delete_user(user_id):
    """Supprime un compte utilisateur ainsi que toutes ses commandes, tickets
    et messages associés (suppression en cascade)."""
    current = get_current_user()
    if current["id"] == user_id:
        flash("Tu ne peux pas supprimer ton propre compte depuis cette page.", "error")
        return redirect(url_for("admin_users"))

    conn = get_db()
    target = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if not target:
        flash("Utilisateur introuvable.", "error")
        conn.close()
        return redirect(url_for("admin_users"))

    target_email = target["email"]

    order_ids = [r["id"] for r in conn.execute("SELECT id FROM orders WHERE user_id = ?", (user_id,)).fetchall()]
    for oid in order_ids:
        conn.execute("DELETE FROM order_messages WHERE order_id = ?", (oid,))
    conn.execute("DELETE FROM orders WHERE user_id = ?", (user_id,))

    ticket_ids = [r["id"] for r in conn.execute("SELECT id FROM tickets WHERE user_id = ?", (user_id,)).fetchall()]
    for tid in ticket_ids:
        conn.execute("DELETE FROM ticket_messages WHERE ticket_id = ?", (tid,))
    conn.execute("DELETE FROM tickets WHERE user_id = ?", (user_id,))

    # Messages écrits par ce compte sur d'autres commandes/tickets (ex: réponses d'un ancien admin)
    conn.execute("DELETE FROM order_messages WHERE author_id = ?", (user_id,))
    conn.execute("DELETE FROM ticket_messages WHERE author_id = ?", (user_id,))

    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()

    flash(f"Compte {target_email} supprimé ({len(order_ids)} commande(s), {len(ticket_ids)} ticket(s)).", "success")
    return redirect(url_for("admin_users"))


# Initialise la base de données dès le chargement du module
# (nécessaire pour Gunicorn/Render qui n'exécute pas le bloc __main__)
init_db()
ensure_admin_account()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
