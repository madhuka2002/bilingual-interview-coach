"""Add LiveKit room bindings and finalized voice transcripts.

Revision ID: 20261111_0004
Revises: 20261111_0003
Create Date: 2026-11-11
"""

import sqlalchemy as sa
from alembic import op

revision: str = "20261111_0004"
down_revision: str | None = "20261111_0003"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "voice_rooms",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("interview_id", sa.Uuid(), nullable=False),
        sa.Column("room_name", sa.String(length=80), nullable=False),
        sa.Column("candidate_identity", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["interview_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("interview_id", name="uq_voice_rooms_interview_id"),
        sa.UniqueConstraint("room_name", name="uq_voice_rooms_room_name"),
        sa.UniqueConstraint(
            "candidate_identity", name="uq_voice_rooms_candidate_identity"
        ),
    )
    op.create_index("ix_voice_rooms_interview_id", "voice_rooms", ["interview_id"])
    op.create_table(
        "voice_transcripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("voice_room_id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.String(length=160), nullable=False),
        sa.Column("participant_identity", sa.String(length=80), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('received', 'processed')",
            name="ck_voice_transcripts_status",
        ),
        sa.ForeignKeyConstraint(
            ["question_id"], ["interview_questions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["voice_room_id"], ["voice_rooms.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "voice_room_id", "event_id", name="uq_voice_transcripts_room_event"
        ),
        sa.UniqueConstraint("question_id", name="uq_voice_transcripts_question_id"),
    )
    op.create_index(
        "ix_voice_transcripts_voice_room_id",
        "voice_transcripts",
        ["voice_room_id"],
    )
    op.create_index(
        "ix_voice_transcripts_question_id", "voice_transcripts", ["question_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_voice_transcripts_question_id", table_name="voice_transcripts")
    op.drop_index("ix_voice_transcripts_voice_room_id", table_name="voice_transcripts")
    op.drop_table("voice_transcripts")
    op.drop_index("ix_voice_rooms_interview_id", table_name="voice_rooms")
    op.drop_table("voice_rooms")
