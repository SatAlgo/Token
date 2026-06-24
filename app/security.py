"""Token (JWT) signing/verification and admin session helpers.

The digital token is a JWT signed with HMAC-SHA256 using SECRET_KEY. Because it's
signed, a customer cannot edit the items/total or forge a token for an order that
was never paid for — any tampering breaks the signature.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt

from .config import settings

ALGORITHM = "HS256"


def new_public_id() -> str:
    """Short, readable order id like 'T-9F3A2C'."""
    return "T-" + secrets.token_hex(3).upper()


def new_jti() -> str:
    """Unique id for a single token, used for server-side revocation."""
    return secrets.token_urlsafe(12)


def issue_token(*, public_id: str, jti: str, items: list[dict], total_paise: int) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": public_id,            # the order this token belongs to
        "jti": jti,                  # unique token id
        "items": items,             # snapshot of what was bought
        "total_paise": total_paise,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.TOKEN_TTL_MINUTES)).timestamp()),
        "shop": settings.SHOP_NAME,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict:
    """Raises jwt.PyJWTError (e.g. ExpiredSignatureError) if invalid."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])


# --- Password hashing (PBKDF2-HMAC-SHA256, standard library) ---------------- #
# Stored format: "pbkdf2$<iterations>$<salt_b64>$<hash_b64>". We never store the
# raw password, and compare with a constant-time check to avoid timing attacks.
_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"pbkdf2${_PBKDF2_ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_b64, hash_b64 = stored.split("$")
        if algo != "pbkdf2":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iters))
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError):
        return False


# --- Staff login sessions (signed cookie, carries the role) ----------------- #
# role is "admin" (the owner, via ADMIN_PASSWORD) or "waiter" (a DB account the
# admin created). The cookie is a short-lived signed JWT — no DB session table.

def issue_session_cookie(role: str, username: str = "") -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "role": role,
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=12)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_session(cookie: str | None) -> dict | None:
    if not cookie:
        return None
    try:
        return jwt.decode(cookie, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
