"""Shared pytest configuration."""

import os
from collections.abc import Generator
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from interview_service.database import get_session
from interview_service.main import app as interview_app
from interview_service.models import Base


@pytest.fixture
def anyio_backend() -> str:
    """Run asynchronous HTTP tests with Python's built-in asyncio backend."""
    return "asyncio"


@pytest.fixture
def database_engine(tmp_path: Path) -> Generator[Engine]:
    """Create a disposable database, refusing non-test PostgreSQL databases."""
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url:
        url = make_url(database_url)
        if url.get_backend_name() == "postgresql" and not (
            url.database and url.database.endswith("_test")
        ):
            pytest.fail("TEST_DATABASE_URL PostgreSQL database must end in '_test'")
        engine = create_engine(database_url, pool_pre_ping=True)
    else:
        database_path = tmp_path / "interviews.sqlite3"
        engine = create_engine(
            f"sqlite:///{database_path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 10},
        )

    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture(autouse=True)
def override_interview_database(database_engine: Engine) -> Generator[None]:
    """Give every interview request its own committed database session."""
    session_factory = sessionmaker(
        bind=database_engine,
        expire_on_commit=False,
    )

    def test_session() -> Generator[Session]:
        with session_factory() as session:
            try:
                yield session
                session.commit()
            except BaseException:
                session.rollback()
                raise

    interview_app.dependency_overrides[get_session] = test_session
    try:
        yield
    finally:
        interview_app.dependency_overrides.clear()
