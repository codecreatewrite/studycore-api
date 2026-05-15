import os
from logging.config import fileConfig
from sqlalchemy import create_engine, pool
from alembic import context

# ── Load .env BEFORE anything else ──────────────────────────────
# Alembic runs as a standalone process — it doesn't go through
# FastAPI's startup, so pydantic-settings never loads the .env.
# We do it manually here, once, at the top.
from dotenv import load_dotenv
load_dotenv()

# ── Load all models so Alembic can detect schema changes ────────
from app.db.base import Base
from app.models import *  # noqa: F401, F403

config = context.config

# ── Pull DATABASE_URL from environment ──────────────────────────
database_url = os.environ.get("DATABASE_URL", "")
if not database_url:
    raise ValueError(
        "DATABASE_URL is not set. "
        "Make sure your .env file exists and contains DATABASE_URL."
    )

# Render/Neon sometimes gives postgres:// — SQLAlchemy needs postgresql://
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)

config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = config.get_main_option("sqlalchemy.url")
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
