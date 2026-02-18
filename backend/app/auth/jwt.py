"""
JWT token creation and validation.

Tokens carry the user's ID and role so that the auth dependency can enforce
authorization without a database round-trip on every request.  The ``sub``
claim holds the user ID as a string; ``role`` is a plain string matching the
UserRole enum value.

Uses python-jose for encoding/decoding with HMAC-SHA256 by default (see
``Settings.jwt_algorithm``).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from pydantic import BaseModel

from app.config import get_settings


class TokenPayload(BaseModel):
    """Parsed contents of a valid access token."""

    user_id: int
    role: str
    exp: datetime


def create_access_token(
    user_id: int,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a signed JWT access token.

    Parameters
    ----------
    user_id:
        Primary key of the authenticated user.
    role:
        Value of the user's ``UserRole`` enum (e.g. ``"admin"``).
    expires_delta:
        Custom token lifetime.  Falls back to ``Settings.jwt_expiry_minutes``
        when ``None``.
    """
    settings = get_settings()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.jwt_expiry_minutes)
    )
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT access token.

    Returns a ``TokenPayload`` on success.  Raises ``ValueError`` if the
    token is malformed, expired, or missing required claims.
    """
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenPayload(
            user_id=int(payload["sub"]),
            role=payload["role"],
            exp=datetime.fromtimestamp(payload["exp"], tz=timezone.utc),
        )
    except (JWTError, KeyError, ValueError) as exc:
        raise ValueError(f"Invalid token: {exc}") from exc
