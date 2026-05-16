from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    APP_ENV: str = "development"
    APP_NAME: str = "StudyCore"
    SECRET_KEY: str
    DATABASE_URL: str
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: str
    GOOGLE_REDIRECT_URI: str
    FRONTEND_URL: str = "http://localhost:3000"
    ACCESS_TOKEN_EXPIRE_DAYS: int = 30
    REFRESH_THRESHOLD_DAYS: int = 7
    TIMEZONE: str = "Africa/Lagos"

    # AI
    GROQ_API_KEY: str = ""

    # Push notifications (VAPID)
    VAPID_PRIVATE_KEY: str = ""
    VAPID_PUBLIC_KEY: str = ""
    VAPID_CLAIMS_EMAIL: str = "mailto:admin@studycore.com.ng"

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
