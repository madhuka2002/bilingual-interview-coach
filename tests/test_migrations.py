"""Alembic migration smoke tests against an isolated database."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_migration_upgrade_and_downgrade(
    tmp_path: Path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "migration.sqlite3"
    database_url = f"sqlite:///{database_path.as_posix()}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    config = Config("alembic.ini")

    engine = create_engine(database_url)
    command.upgrade(config, "20261111_0002")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO interview_sessions "
                "(id, mode, language, status, max_questions) "
                "VALUES (:id, 'mock_interview', 'en', 'created', 5)"
            ),
            {"id": "11111111111141118111111111111111"},
        )
    command.upgrade(config, "head")

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
        "target_role",
        "experience_level",
        "category",
        "difficulty",
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
    evaluation_columns = {
        column["name"] for column in inspector.get_columns("answer_evaluations")
    }
    assert {"criteria", "learning_areas"} <= evaluation_columns
    with engine.connect() as connection:
        migrated = connection.execute(
            text(
                "SELECT target_role, experience_level, category, difficulty "
                "FROM interview_sessions"
            )
        ).one()
    assert migrated == ("Software Engineer", "mid", "mixed", "intermediate")

    command.downgrade(config, "20261111_0002")
    inspector = inspect(engine)
    session_columns = {
        column["name"] for column in inspector.get_columns("interview_sessions")
    }
    evaluation_columns = {
        column["name"] for column in inspector.get_columns("answer_evaluations")
    }
    assert "target_role" not in session_columns
    assert "criteria" not in evaluation_columns

    command.upgrade(config, "head")

    command.downgrade(config, "base")

    assert "interview_sessions" not in inspect(engine).get_table_names()
    engine.dispose()
