from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_ENV: str = "development"
    APP_NAME: str = "StudyCore"
    SECRET_KEY: str

    # Database
    DATABASE_URL: str

    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str

    # CORS
    FRONTEND_URL: str = "http://localhost:3000"

    # JWT
    ACCESS_TOKEN_EXPIRE_DAYS: int = 30
    REFRESH_THRESHOLD_DAYS: int = 7

    # Timezone
    TIMEZONE: str = "Africa/Lagos"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
