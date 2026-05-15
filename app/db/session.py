from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings


def _build_engine_url(url: str) -> str:
    """
    Neon gives a pooler URL for the app (high concurrency, efficient).
    psycopg2 needs the URL cleaned of unsupported params.
    Remove channel_binding if present — psycopg2 doesn't support it.
    """
    # Strip unsupported params
    if "channel_binding" in url:
        import re
        url = re.sub(r"[&?]channel_binding=[^&]*", "", url)
        # Clean up trailing ? or & if it was the only param
        url = url.rstrip("?&")
    return url


engine = create_engine(
    _build_engine_url(settings.DATABASE_URL),
    pool_pre_ping=True,
    pool_recycle=300,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    echo=settings.APP_ENV == "development",
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
