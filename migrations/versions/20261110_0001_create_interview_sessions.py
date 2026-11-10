"""Create persistent interview sessions.

Revision ID: 20261110_0001
Revises:
Create Date: 2026-11-10
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261110_0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "interview_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'created'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "mode IN ('mock_interview', 'career_coach')",
            name="ck_interview_sessions_mode",
        ),
        sa.CheckConstraint(
            "language IN ('en', 'si')",
            name="ck_interview_sessions_language",
        ),
        sa.CheckConstraint(
            "status IN ('created', 'active', 'completed')",
            name="ck_interview_sessions_status",
        ),
        sa.CheckConstraint(
            "(status = 'created' AND started_at IS NULL AND completed_at IS NULL) "
            "OR (status = 'active' AND started_at IS NOT NULL "
            "AND completed_at IS NULL) "
            "OR (status = 'completed' AND started_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="ck_interview_sessions_lifecycle_timestamps",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_interview_sessions_timestamp_order",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_interview_sessions_created_at",
        "interview_sessions",
        ["created_at"],
    )
    op.create_index(
        "ix_interview_sessions_status",
        "interview_sessions",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_interview_sessions_status", table_name="interview_sessions")
    op.drop_index("ix_interview_sessions_created_at", table_name="interview_sessions")
    op.drop_table("interview_sessions")
