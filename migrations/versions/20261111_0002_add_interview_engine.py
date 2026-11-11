"""Add interview questions, answers, evaluations, and summaries.

Revision ID: 20261111_0002
Revises: 20261110_0001
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261111_0002"
down_revision: str | None = "20261110_0001"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "interview_sessions",
        sa.Column(
            "max_questions",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("5"),
        ),
    )
    with op.batch_alter_table("interview_sessions") as batch_op:
        batch_op.create_check_constraint(
            "ck_interview_sessions_max_questions",
            "max_questions >= 1 AND max_questions <= 20",
        )

    op.create_table(
        "interview_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("topic", sa.String(length=120), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint("sequence >= 1", name="ck_interview_questions_sequence"),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interview_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "interview_id",
            "sequence",
            name="uq_interview_questions_interview_sequence",
        ),
    )
    op.create_index(
        "ix_interview_questions_interview_id",
        "interview_questions",
        ["interview_id"],
    )

    op.create_table(
        "candidate_answers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["question_id"],
            ["interview_questions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", name="uq_candidate_answers_question_id"),
    )
    op.create_index(
        "ix_candidate_answers_question_id",
        "candidate_answers",
        ["question_id"],
    )

    op.create_table(
        "answer_evaluations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("answer_id", sa.Uuid(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("feedback", sa.Text(), nullable=False),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("improvements", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_answer_evaluations_score",
        ),
        sa.ForeignKeyConstraint(
            ["answer_id"],
            ["candidate_answers.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("answer_id", name="uq_answer_evaluations_answer_id"),
    )
    op.create_index(
        "ix_answer_evaluations_answer_id",
        "answer_evaluations",
        ["answer_id"],
    )

    op.create_table(
        "interview_summaries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("overall_score", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("strengths", sa.JSON(), nullable=False),
        sa.Column("improvements", sa.JSON(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_interview_summaries_overall_score",
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"],
            ["interview_sessions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "interview_id",
            name="uq_interview_summaries_interview_id",
        ),
    )
    op.create_index(
        "ix_interview_summaries_interview_id",
        "interview_summaries",
        ["interview_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_interview_summaries_interview_id",
        table_name="interview_summaries",
    )
    op.drop_table("interview_summaries")
    op.drop_index(
        "ix_answer_evaluations_answer_id",
        table_name="answer_evaluations",
    )
    op.drop_table("answer_evaluations")
    op.drop_index(
        "ix_candidate_answers_question_id",
        table_name="candidate_answers",
    )
    op.drop_table("candidate_answers")
    op.drop_index(
        "ix_interview_questions_interview_id",
        table_name="interview_questions",
    )
    op.drop_table("interview_questions")
    with op.batch_alter_table("interview_sessions") as batch_op:
        batch_op.drop_constraint(
            "ck_interview_sessions_max_questions",
            type_="check",
        )
        batch_op.drop_column("max_questions")
