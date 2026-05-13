from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from app.core.config import settings


def create_access_token(user_id: str) -> str:
    """Create a 30-day JWT for the given user ID."""
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.ACCESS_TOKEN_EXPIRE_DAYS
    )
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate JWT. Returns payload or None."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        return None


def should_refresh_token(payload: dict) -> bool:
    """
    Returns True if the token expires in less than REFRESH_THRESHOLD_DAYS.
    Used to silently renew the cookie so active users never get logged out.
    """
    exp = payload.get("exp")
    if not exp:
        return False
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    return (expires_at - datetime.now(timezone.utc)) < timedelta(
        days=settings.REFRESH_THRESHOLD_DAYS
    )


# Cookie configuration — single source of truth
COOKIE_CONFIG = {
    "key": "sc_token",
    "httponly": True,
    "secure": True,       # HTTPS only
    "samesite": "lax",    # CSRF protection
    "max_age": 30 * 24 * 3600,  # 30 days in seconds
}
