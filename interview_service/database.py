"""Database configuration and request-scoped SQLAlchemy sessions."""

import os
from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL_ENV = "DATABASE_URL"


def get_database_url() -> str:
    """Return the configured database URL without embedding credentials."""
    database_url = os.getenv(DATABASE_URL_ENV)
    if not database_url:
        raise RuntimeError(f"{DATABASE_URL_ENV} must be set for the interview service")
    return database_url


def create_db_engine(database_url: str | None = None) -> Engine:
    """Create an engine for the configured database."""
    return create_engine(
        database_url or get_database_url(),
        pool_pre_ping=True,
    )


@lru_cache
def get_engine() -> Engine:
    """Create the process-wide connection pool on first database use."""
    return create_db_engine()


def get_session() -> Generator[Session]:
    """Provide one transaction per request, rolling back on any failure."""
    session_factory = sessionmaker(
        bind=get_engine(),
        expire_on_commit=False,
    )
    with session_factory() as session:
        try:
            yield session
            session.commit()
        except BaseException:
            session.rollback()
            raise
