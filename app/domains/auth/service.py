"""
Google OAuth implementation using httpx (no Google SDK required).
Lighter, no hidden dependencies, full control.
"""
import httpx
from sqlalchemy.orm import Session
from app.models.user import User, OAuthState
from app.core.config import settings
import secrets


GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

SCOPES = "openid email profile"


class AuthService:

    @staticmethod
    def create_oauth_state(db: Session) -> str:
        """
        Generate a cryptographically secure state token,
        persist it in the DB, and return it.
        DB storage fixes the multi-worker race condition.
        """
        state = secrets.token_urlsafe(32)
        db.add(OAuthState(state=state))
        db.commit()
        return state

    @staticmethod
    def validate_and_consume_state(db: Session, state: str) -> bool:
        """
        Verify the state exists, then delete it (one-time use).
        Returns True if valid, False if not found (possible CSRF).
        """
        record = db.query(OAuthState).filter(OAuthState.state == state).first()
        if not record:
            return False
        db.delete(record)
        db.commit()
        return True

    @staticmethod
    def get_authorization_url(state: str) -> str:
        """Build the Google OAuth consent URL."""
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": settings.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": SCOPES,
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
        }
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return f"{GOOGLE_AUTH_URL}?{query}"

    @staticmethod
    def exchange_code(code: str) -> dict:
        """Exchange the authorization code for tokens."""
        with httpx.Client() as client:
            resp = client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def get_google_user(access_token: str) -> dict:
        """Fetch the authenticated user's profile from Google."""
        with httpx.Client() as client:
            resp = client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    def get_or_create_user(db: Session, google_user: dict) -> User:
        """
        Look up user by google_id. Create if first login.
        Update last_login on every successful auth.
        """
        user = (
            db.query(User)
            .filter(User.google_id == google_user["id"])
            .first()
        )

        if not user:
            user = User(
                google_id=google_user["id"],
                email=google_user["email"],
                name=google_user.get("name", ""),
                picture=google_user.get("picture"),
            )
            db.add(user)

        # Always update last_login
        from datetime import datetime, timezone
        user.last_login = datetime.now(timezone.utc)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def cleanup_expired_states(db: Session):
        """
        Delete OAuth states older than 10 minutes.
        Called on each callback to prevent state table bloat.
        """
        from datetime import datetime, timezone, timedelta
        from sqlalchemy import delete
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        db.execute(
            delete(OAuthState).where(OAuthState.created_at < cutoff)
        )
        db.commit()
