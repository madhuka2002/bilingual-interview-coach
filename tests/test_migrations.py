"""Alembic migration smoke tests against an isolated database."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def test_migration_upgrade_and_downgrade(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")

    command.upgrade(config, "head")

    engine = create_engine(database_url)
    inspector = inspect(engine)
    assert "interview_sessions" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("interview_sessions")}
    assert columns == {
        "id",
        "mode",
        "language",
        "status",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "max_questions",
    }
    assert {index["name"] for index in inspector.get_indexes("interview_sessions")} == {
        "ix_interview_sessions_created_at",
        "ix_interview_sessions_status",
    }
    assert {
        "answer_evaluations",
        "candidate_answers",
        "interview_questions",
        "interview_sessions",
        "interview_summaries",
    } <= set(inspector.get_table_names())

    command.downgrade(config, "base")

    assert "interview_sessions" not in inspect(engine).get_table_names()
    engine.dispose()
