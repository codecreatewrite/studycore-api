from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import create_access_token, COOKIE_CONFIG
from app.core.dependencies import get_current_user, get_current_user_optional
from app.domains.auth.service import AuthService
from app.domains.auth.schemas import AuthStatusResponse, UserResponse
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(db: Session = Depends(get_db)):
    """
    Step 1 of OAuth: generate state, redirect to Google consent.
    State is stored in DB — fixes the multi-worker race condition.
    """
    state = AuthService.create_oauth_state(db)
    url = AuthService.get_authorization_url(state)
    return RedirectResponse(url=url)


@router.get("/callback")
def auth_callback(
    code: str,
    state: str,
    response: Response,
    db: Session = Depends(get_db),
):
    """
    Step 2 of OAuth: validate state, exchange code, create/update user,
    set httponly cookie, redirect to frontend dashboard.
    """
    # Clean up expired states (housekeeping)
    AuthService.cleanup_expired_states(db)

    # Validate state — prevents CSRF
    if not AuthService.validate_and_consume_state(db, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state. Please try logging in again.")

    try:
        token_data = AuthService.exchange_code(code)
        google_user = AuthService.get_google_user(token_data["access_token"])
        user = AuthService.get_or_create_user(db, google_user)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Authentication failed: {str(e)}",
        )

    # Issue our own JWT
    access_token = create_access_token(user.id)

    # Redirect to frontend with cookie set
    redirect = RedirectResponse(
        url=f"{settings.FRONTEND_URL}/dashboard",
        status_code=302,
    )
    redirect.set_cookie(value=access_token, **COOKIE_CONFIG)
    return redirect


@router.get("/logout")
def logout(response: Response):
    """Clear the auth cookie and redirect to frontend home."""
    redirect = RedirectResponse(url=settings.FRONTEND_URL, status_code=302)
    redirect.delete_cookie("sc_token")
    return redirect


@router.get("/me", response_model=AuthStatusResponse)
def get_me(user=Depends(get_current_user_optional)):
    """
    Frontend calls this on load to check auth status.
    Returns user data if authenticated, or authenticated: false.
    """
    if not user:
        return AuthStatusResponse(authenticated=False)
    return AuthStatusResponse(
        authenticated=True,
        user=UserResponse.model_validate(user),
    )
