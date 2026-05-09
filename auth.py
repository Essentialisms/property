"""User authentication: SQLite-backed user store + Flask-Login integration."""

import os
import sqlite3
import secrets
import logging
from datetime import datetime, timezone
from contextlib import contextmanager

from flask import Blueprint, render_template, request, redirect, url_for, flash, g
from flask_login import (
    LoginManager,
    UserMixin,
    login_user,
    logout_user,
    login_required,
    current_user,
)
from werkzeug.security import generate_password_hash, check_password_hash

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("USERS_DB_PATH", "/tmp/users.db")

login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access agentic search."

bp = Blueprint("auth", __name__)


# ===== DB helpers =====

@contextmanager
def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    """Create the users table if it doesn't exist."""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    with _conn() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                stripe_customer_id TEXT,
                subscription_id TEXT,
                subscription_status TEXT,
                subscription_plan TEXT,
                current_period_end INTEGER,
                created_at TEXT NOT NULL
            )
            """
        )


# ===== User model =====

class User(UserMixin):
    def __init__(self, row: sqlite3.Row):
        self.id = row["id"]
        self.email = row["email"]
        self.password_hash = row["password_hash"]
        self.stripe_customer_id = row["stripe_customer_id"]
        self.subscription_id = row["subscription_id"]
        self.subscription_status = row["subscription_status"]
        self.subscription_plan = row["subscription_plan"]
        self.current_period_end = row["current_period_end"]

    def get_id(self) -> str:
        return str(self.id)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def has_active_subscription(self) -> bool:
        return self.subscription_status in ("active", "trialing")


def find_user_by_id(user_id: int) -> User | None:
    with _conn() as con:
        row = con.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return User(row) if row else None


def find_user_by_email(email: str) -> User | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()
        return User(row) if row else None


def find_user_by_stripe_customer(customer_id: str) -> User | None:
    with _conn() as con:
        row = con.execute(
            "SELECT * FROM users WHERE stripe_customer_id = ?", (customer_id,)
        ).fetchone()
        return User(row) if row else None


def create_user(email: str, password: str) -> User:
    pw_hash = generate_password_hash(password)
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (email.lower().strip(), pw_hash, now),
        )
        user_id = cur.lastrowid
    user = find_user_by_id(user_id)
    assert user is not None
    return user


def set_stripe_customer(user_id: int, customer_id: str) -> None:
    with _conn() as con:
        con.execute(
            "UPDATE users SET stripe_customer_id = ? WHERE id = ?",
            (customer_id, user_id),
        )


def update_subscription(
    customer_id: str,
    subscription_id: str | None,
    status: str | None,
    plan: str | None,
    current_period_end: int | None,
) -> None:
    with _conn() as con:
        con.execute(
            """
            UPDATE users
               SET subscription_id = ?,
                   subscription_status = ?,
                   subscription_plan = ?,
                   current_period_end = ?
             WHERE stripe_customer_id = ?
            """,
            (subscription_id, status, plan, current_period_end, customer_id),
        )


# ===== Flask-Login wiring =====

@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    try:
        return find_user_by_id(int(user_id))
    except (TypeError, ValueError):
        return None


def init_app(app) -> None:
    """Attach Flask-Login + ensure secret key + create DB."""
    if not app.secret_key:
        app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)
    login_manager.init_app(app)
    init_db()
    app.register_blueprint(bp)


# ===== Routes =====

@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""

        if not email or "@" not in email:
            flash("Please enter a valid email address.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif find_user_by_email(email):
            flash("An account with that email already exists.", "error")
        else:
            user = create_user(email, password)
            login_user(user)
            return redirect(url_for("payments.pricing"))

    return render_template("signup.html")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("index"))

    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        user = find_user_by_email(email)
        if user and user.check_password(password):
            login_user(user)
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)
        flash("Invalid email or password.", "error")

    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@bp.route("/account")
@login_required
def account():
    return render_template("account.html", user=current_user)
