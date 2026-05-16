from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.core.security import create_access_token, COOKIE_CONFIG
from app.core.dependencies import get_current_user, get_current_user_optional
from app.domains.auth.service import AuthService
from app.domains.auth.schemas import AuthStatusResponse, UserResponse
from app.models.user import User
from app.core.config import settings

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(db: Session = Depends(get_db)):
    state = AuthService.create_oauth_state(db)
    url = AuthService.get_authorization_url(state)
    return RedirectResponse(url=url)


@router.get("/callback")
def auth_callback(
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    AuthService.cleanup_expired_states(db)

    if not AuthService.validate_and_consume_state(db, state):
        raise HTTPException(status_code=400, detail="Invalid OAuth state.")

    try:
        token_data = AuthService.exchange_code(code)
        google_user = AuthService.get_google_user(token_data["access_token"])
        user = AuthService.get_or_create_user(db, google_user)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Authentication failed: {str(e)}")

    access_token = create_access_token(user.id)

    # Choose redirect destination based on onboarding status
    destination = (
        f"{settings.FRONTEND_URL}/dashboard"
        if user.onboarding_completed
        else f"{settings.FRONTEND_URL}/onboarding"
    )

    # Use an HTML page with JS to set the cookie and redirect.
    # This works cross-domain where a direct redirect + Set-Cookie
    # gets blocked by the browser's SameSite policy.
    html = f"""
<!DOCTYPE html>
<html>
<head><title>Signing in...</title></head>
<body>
<script>
  window.location.href = "{settings.FRONTEND_URL}/auth/callback#token={access_token}";
</script>
<p>Signing you in...</p>
</body>
</html>
"""
    return HTMLResponse(content=html)

@router.get("/logout")
def logout():
    redirect = RedirectResponse(url=settings.FRONTEND_URL, status_code=302)
    redirect.delete_cookie("sc_token", samesite="none", secure=True)
    return redirect


@router.get("/me", response_model=AuthStatusResponse)
def get_me(user=Depends(get_current_user_optional)):
    if not user:
        return AuthStatusResponse(authenticated=False)
    return AuthStatusResponse(
        authenticated=True,
        user=UserResponse.model_validate(user),
    )

@router.post("/onboarding-complete")
def complete_onboarding(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Called after the user completes their first recall session."""
    user.onboarding_completed = True
    db.commit()
    return {"success": True}
