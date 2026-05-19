"""
auth.py — Authentification par code d'accès + gestion des crédits.

Stockage : SQLite (fichier auth.db). Sessions : cookie HttpOnly.

Premier démarrage :
  - Si la table users est vide, un compte admin est créé.
  - Le code admin est soit ADMIN_CODE (env var), soit généré aléatoirement
    et imprimé dans la console.
"""

import os
import sqlite3
import secrets
import time
from contextlib import contextmanager
from typing import Optional

from fastapi import Cookie, Depends, HTTPException

# Dossier où stocker la base SQLite. Configurable via DATA_DIR (utile en
# Docker pour pointer vers un volume monté). Par défaut : à côté de auth.py.
_DATA_DIR = os.getenv("DATA_DIR", os.path.dirname(__file__))
os.makedirs(_DATA_DIR, exist_ok=True)
DB_PATH = os.path.join(_DATA_DIR, "auth.db")

SESSION_COOKIE = "transcription_session"
SESSION_DURATION = 7 * 24 * 3600  # 7 jours

DEFAULT_CREDITS = int(os.getenv("DEFAULT_CREDITS", "30"))
COST_SIMPLE     = int(os.getenv("COST_SIMPLE",     "5"))
COST_DIARIZE    = int(os.getenv("COST_DIARIZE",   "10"))
ADMIN_CONTACT   = os.getenv("ADMIN_CONTACT", "").strip()


# ─── Connexion DB ─────────────────────────────────────────────────────────────

@contextmanager
def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with _get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                code         TEXT UNIQUE NOT NULL,
                name         TEXT,
                credits      INTEGER NOT NULL DEFAULT 0,
                is_admin     INTEGER NOT NULL DEFAULT 0,
                created_at   INTEGER NOT NULL,
                last_used_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token      TEXT PRIMARY KEY,
                user_id    INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS usage_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL,
                action        TEXT NOT NULL,
                credits_delta INTEGER NOT NULL,
                detail        TEXT,
                created_at    INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS purchases (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                purchase_ref     TEXT UNIQUE NOT NULL,   -- réf interne envoyée à Chariow
                chariow_sale_id  TEXT,                   -- sal_xxx renvoyé par Chariow
                plan             TEXT NOT NULL,          -- "standard" | "premium"
                amount           INTEGER,                -- montant en XOF
                customer_email   TEXT NOT NULL,
                customer_name    TEXT,
                customer_phone   TEXT,
                status           TEXT NOT NULL,          -- pending | paid | failed | abandoned
                user_id          INTEGER,                -- user créé après paiement
                user_code        TEXT,                   -- code utilisateur généré
                credits_granted  INTEGER,
                created_at       INTEGER NOT NULL,
                fulfilled_at     INTEGER,
                webhook_payload  TEXT,                   -- dernier payload reçu (debug)
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
        """)
        conn.commit()


# ─── Génération de code ───────────────────────────────────────────────────────

_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sans I, O, L, 0, 1


def generate_code(length: int = 8) -> str:
    """Code lisible au format ABCD-1234."""
    s = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))
    return f"{s[:4]}-{s[4:]}"


def _unique_code() -> str:
    for _ in range(20):
        code = generate_code()
        with _get_conn() as conn:
            row = conn.execute("SELECT 1 FROM users WHERE code = ?", (code,)).fetchone()
        if not row:
            return code
    raise RuntimeError("Impossible de générer un code unique")


# ─── CRUD Users ───────────────────────────────────────────────────────────────

def create_user(
    name: Optional[str] = None,
    credits: int = None,
    is_admin: bool = False,
    code: Optional[str] = None,
) -> dict:
    if credits is None:
        credits = DEFAULT_CREDITS
    code = (code or _unique_code()).strip().upper()
    with _get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (code, name, credits, is_admin, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (code, name, credits, 1 if is_admin else 0, int(time.time())),
        )
        conn.commit()
        user_id = cur.lastrowid
    return get_user_by_id(user_id)


def get_user_by_id(user_id: int) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None


def get_user_by_code(code: str) -> Optional[dict]:
    code = code.strip().upper()
    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE code = ?", (code,)).fetchone()
        return dict(row) if row else None


def list_users() -> list:
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY is_admin DESC, created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def add_credits(user_id: int, delta: int, reason: str = "admin_add") -> Optional[dict]:
    user = get_user_by_id(user_id)
    if not user:
        return None
    with _get_conn() as conn:
        conn.execute(
            "UPDATE users SET credits = credits + ? WHERE id = ?",
            (delta, user_id),
        )
        conn.execute(
            "INSERT INTO usage_log (user_id, action, credits_delta, created_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, reason, delta, int(time.time())),
        )
        conn.commit()
    return get_user_by_id(user_id)


def deduct_credits(user_id: int, amount: int, action: str = "transcribe") -> bool:
    """Retourne True si le débit a réussi, False si crédits insuffisants."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT credits, is_admin FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not row:
            return False
        # L'admin a des crédits illimités (pas de débit)
        if row["is_admin"]:
            conn.execute(
                "UPDATE users SET last_used_at = ? WHERE id = ?",
                (int(time.time()), user_id),
            )
            conn.commit()
            return True
        if row["credits"] < amount:
            return False
        conn.execute(
            "UPDATE users SET credits = credits - ?, last_used_at = ? WHERE id = ?",
            (amount, int(time.time()), user_id),
        )
        conn.execute(
            "INSERT INTO usage_log (user_id, action, credits_delta, created_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, action, -amount, int(time.time())),
        )
        conn.commit()
    return True


def refund_credits(user_id: int, amount: int, reason: str = "refund_error") -> None:
    user = get_user_by_id(user_id)
    if not user or user["is_admin"]:
        return
    with _get_conn() as conn:
        conn.execute(
            "UPDATE users SET credits = credits + ? WHERE id = ?",
            (amount, user_id),
        )
        conn.execute(
            "INSERT INTO usage_log (user_id, action, credits_delta, created_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, reason, amount, int(time.time())),
        )
        conn.commit()


def delete_user(user_id: int) -> bool:
    user = get_user_by_id(user_id)
    if not user or user["is_admin"]:
        return False
    with _get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
    return True


# ─── Sessions ─────────────────────────────────────────────────────────────────

def create_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + SESSION_DURATION
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO sessions (token, user_id, expires_at) VALUES (?, ?, ?)",
            (token, user_id, expires_at),
        )
        conn.commit()
    return token


def get_user_by_session(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT u.* FROM sessions s "
            "JOIN users u ON s.user_id = u.id "
            "WHERE s.token = ? AND s.expires_at > ?",
            (token, int(time.time())),
        ).fetchone()
        return dict(row) if row else None


def delete_session(token: str) -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def cleanup_expired_sessions() -> None:
    with _get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at <= ?", (int(time.time()),))
        conn.commit()


# ─── Achats (Chariow) ─────────────────────────────────────────────────────────

def create_purchase(
    purchase_ref: str,
    plan: str,
    customer_email: str,
    customer_name: Optional[str] = None,
    customer_phone: Optional[str] = None,
    amount: Optional[int] = None,
) -> dict:
    """Crée une ligne purchase au statut 'pending' avant la redirection Chariow."""
    with _get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO purchases
                (purchase_ref, plan, amount, customer_email, customer_name,
                 customer_phone, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (purchase_ref, plan, amount, customer_email, customer_name,
             customer_phone, int(time.time())),
        )
        conn.commit()
        purchase_id = cur.lastrowid
    return get_purchase_by_id(purchase_id)


def get_purchase_by_id(purchase_id: int) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM purchases WHERE id = ?", (purchase_id,)
        ).fetchone()
        return dict(row) if row else None


def get_purchase_by_ref(purchase_ref: str) -> Optional[dict]:
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM purchases WHERE purchase_ref = ?", (purchase_ref,)
        ).fetchone()
        return dict(row) if row else None


def update_purchase_sale_id(purchase_ref: str, chariow_sale_id: str) -> None:
    with _get_conn() as conn:
        conn.execute(
            "UPDATE purchases SET chariow_sale_id = ? WHERE purchase_ref = ?",
            (chariow_sale_id, purchase_ref),
        )
        conn.commit()


def fulfill_purchase(
    purchase_ref: str,
    credits: int,
    webhook_payload: Optional[str] = None,
) -> Optional[dict]:
    """
    Crée le code utilisateur correspondant à un paiement réussi, lie le user
    au purchase, et marque le purchase comme 'paid'.

    Idempotent : si le purchase est déjà 'paid', renvoie le user existant.
    Retourne le user créé (ou existant) avec sa clé d'accès.
    """
    purchase = get_purchase_by_ref(purchase_ref)
    if not purchase:
        return None

    # Idempotence : déjà traité
    if purchase["status"] == "paid" and purchase["user_id"]:
        return get_user_by_id(purchase["user_id"])

    # Création du code utilisateur
    user = create_user(
        name=purchase["customer_name"] or purchase["customer_email"],
        credits=credits,
        is_admin=False,
    )

    with _get_conn() as conn:
        conn.execute(
            """
            UPDATE purchases
            SET status = 'paid',
                user_id = ?,
                user_code = ?,
                credits_granted = ?,
                fulfilled_at = ?,
                webhook_payload = ?
            WHERE purchase_ref = ?
            """,
            (user["id"], user["code"], credits, int(time.time()),
             webhook_payload, purchase_ref),
        )
        conn.execute(
            "INSERT INTO usage_log (user_id, action, credits_delta, detail, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (user["id"], "purchase_fulfilled", credits,
             f"plan={purchase['plan']} ref={purchase_ref}", int(time.time())),
        )
        conn.commit()
    return user


def mark_purchase_status(
    purchase_ref: str, status: str, webhook_payload: Optional[str] = None,
) -> None:
    """Marque un purchase 'failed' ou 'abandoned' (idempotent)."""
    with _get_conn() as conn:
        conn.execute(
            "UPDATE purchases SET status = ?, webhook_payload = ? "
            "WHERE purchase_ref = ? AND status NOT IN ('paid')",
            (status, webhook_payload, purchase_ref),
        )
        conn.commit()


# ─── Bootstrap admin ──────────────────────────────────────────────────────────

def ensure_admin_user() -> None:
    """Crée le compte admin au premier démarrage si la base est vide."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE is_admin = 1"
        ).fetchone()
    if row["n"] > 0:
        return

    custom_code = os.getenv("ADMIN_CODE", "").strip().upper() or None
    admin = create_user(
        name="Admin",
        credits=0,  # ignoré (admin = illimité)
        is_admin=True,
        code=custom_code,
    )
    msg_lines = [
        "",
        "================================================",
        "  COMPTE ADMIN CREE",
        f"  Code : {admin['code']}",
        "  Notez-le ! Utilisez-le pour vous connecter",
        "  sur http://localhost:8000/app/admin.html",
        "================================================",
        "",
    ]
    for line in msg_lines:
        try:
            print(line)
        except UnicodeEncodeError:
            print(line.encode("ascii", "replace").decode("ascii"))


# ─── Dépendances FastAPI ──────────────────────────────────────────────────────

def current_user_optional(
    transcription_session: Optional[str] = Cookie(default=None),
) -> Optional[dict]:
    return get_user_by_session(transcription_session)


def require_user(
    user: Optional[dict] = Depends(current_user_optional),
) -> dict:
    if not user:
        raise HTTPException(status_code=401, detail="Connexion requise")
    return user


def require_admin(user: dict = Depends(require_user)) -> dict:
    if not user.get("is_admin"):
        raise HTTPException(status_code=403, detail="Accès réservé à l'administrateur")
    return user


# ─── Sérialisation publique ───────────────────────────────────────────────────

def user_public(user: dict, include_code: bool = False) -> dict:
    out = {
        "id":       user["id"],
        "name":     user.get("name"),
        "credits":  user["credits"],
        "is_admin": bool(user["is_admin"]),
    }
    if include_code:
        out["code"]         = user["code"]
        out["created_at"]   = user["created_at"]
        out["last_used_at"] = user.get("last_used_at")
    return out
