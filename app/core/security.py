from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from app.core.config import settings

ALGORITHM = "HS256"

def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.ACCESS_TOKEN_EXPIRE_DAYS
    )
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def should_refresh_token(payload: dict) -> bool:
    exp = payload.get("exp")
    if not exp:
        return False
    expires_at = datetime.fromtimestamp(exp, tz=timezone.utc)
    return (expires_at - datetime.now(timezone.utc)) < timedelta(
        days=settings.REFRESH_THRESHOLD_DAYS
    )


# Cross-domain cookie config
# SameSite=none + Secure=True required for cookie to work
# across different domains (Vercel frontend → Render backend)
COOKIE_CONFIG = {
    "key": "sc_token",
    "httponly": True,
    "secure": True,
    "samesite": "none",   # CHANGED from "lax" to "none" for cross-domain
    "max_age": 30 * 24 * 3600,
}
