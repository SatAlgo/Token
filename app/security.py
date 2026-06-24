"""Token (JWT) signing/verification and admin session helpers.

The digital token is a JWT signed with HMAC-SHA256 using SECRET_KEY. Because it's
signed, a customer cannot edit the items/total or forge a token for an order that
was never paid for — any tampering breaks the signature.
"""
from __future__ import annotations

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


# --- Admin / waiter login (signed cookie, no DB session table needed) ---

def issue_session_cookie() -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "role": "staff",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=12)).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def is_valid_session(cookie: str | None) -> bool:
    if not cookie:
        return False
    try:
        data = jwt.decode(cookie, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return data.get("role") == "staff"
    except jwt.PyJWTError:
        return False
