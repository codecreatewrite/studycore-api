# Import all models here so Alembic can detect them for migrations.
from app.models.user import User, OAuthState

__all__ = ["User", "OAuthState"]
