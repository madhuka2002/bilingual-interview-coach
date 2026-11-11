"""Add configurable bilingual interviews and structured evaluation details.

Revision ID: 20261111_0003
Revises: 20261111_0002
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261111_0003"
down_revision: str | None = "20261111_0002"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.batch_alter_table("interview_sessions") as batch_op:
        batch_op.add_column(
            sa.Column(
                "target_role",
                sa.String(length=120),
                nullable=False,
                server_default="Software Engineer",
            )
        )
        batch_op.add_column(
            sa.Column(
                "experience_level",
                sa.String(length=16),
                nullable=False,
                server_default="mid",
            )
        )
        batch_op.add_column(
            sa.Column(
                "category",
                sa.String(length=16),
                nullable=False,
                server_default="mixed",
            )
        )
        batch_op.add_column(
            sa.Column(
                "difficulty",
                sa.String(length=16),
                nullable=False,
                server_default="intermediate",
            )
        )
        batch_op.create_check_constraint(
            "ck_interview_sessions_experience_level",
            "experience_level IN ('entry', 'mid', 'senior')",
        )
        batch_op.create_check_constraint(
            "ck_interview_sessions_category",
            "category IN ('technical', 'behavioral', 'hr', 'mixed')",
        )
        batch_op.create_check_constraint(
            "ck_interview_sessions_difficulty",
            "difficulty IN ('beginner', 'intermediate', 'advanced')",
        )

    with op.batch_alter_table("answer_evaluations") as batch_op:
        batch_op.add_column(
            sa.Column(
                "criteria",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            )
        )
        batch_op.add_column(
            sa.Column(
                "learning_areas",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'[]'"),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("answer_evaluations") as batch_op:
        batch_op.drop_column("learning_areas")
        batch_op.drop_column("criteria")

    with op.batch_alter_table("interview_sessions") as batch_op:
        batch_op.drop_constraint("ck_interview_sessions_difficulty", type_="check")
        batch_op.drop_constraint("ck_interview_sessions_category", type_="check")
        batch_op.drop_constraint(
            "ck_interview_sessions_experience_level", type_="check"
        )
        batch_op.drop_column("difficulty")
        batch_op.drop_column("category")
        batch_op.drop_column("experience_level")
        batch_op.drop_column("target_role")
