from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# Neon requires SSL — the URL from Neon already includes ?sslmode=require
engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,      # Detect stale connections before use
    pool_recycle=300,        # Recycle connections every 5 min (Neon idle timeout)
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    echo=settings.APP_ENV == "development",  # Log SQL in dev only
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency: yields a DB session, always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
