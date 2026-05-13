from fastapi import Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import (
    decode_access_token,
    create_access_token,
    should_refresh_token,
    COOKIE_CONFIG,
)
from app.models.user import User
from typing import Optional


def _extract_token(request: Request) -> Optional[str]:
    """Pull JWT from the httponly cookie."""
    return request.cookies.get("sc_token")


def get_current_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency: returns the authenticated User.
    Silently refreshes the cookie if < REFRESH_THRESHOLD_DAYS remain.
    Raises 401 if not authenticated or token invalid.
    """
    token = _extract_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user_id: str = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token",
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    # Silent refresh: renew cookie if close to expiry
    if should_refresh_token(payload):
        new_token = create_access_token(user_id)
        response.set_cookie(value=new_token, **COOKIE_CONFIG)

    return user


def get_current_user_optional(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Optional auth — returns None if not authenticated."""
    try:
        return get_current_user(request, response, db)
    except HTTPException:
        return None
