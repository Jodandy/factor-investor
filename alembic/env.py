"""Alembic environment configuration."""

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from factor_investor.ingest.models import Base  # noqa: E402
# Import all models so they're registered with Base.metadata
import factor_investor.ingest.models  # noqa: E402, F401
import factor_investor.pit.models  # noqa: E402, F401
import factor_investor.universe.models  # noqa: E402, F401
import factor_investor.factors.models  # noqa: E402, F401
import factor_investor.search.models  # noqa: E402, F401

load_dotenv()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Override sqlalchemy.url with environment variable if set
database_url = os.getenv("DATABASE_URL")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
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
    """Run migrations in 'online' mode."""
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),  # type: ignore[arg-type]
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
