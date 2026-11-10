"""SQLAlchemy models for persistent interview data."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, Index, String, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base class for database models."""


class InterviewMode(StrEnum):
    MOCK_INTERVIEW = "mock_interview"
    CAREER_COACH = "career_coach"


class InterviewLanguage(StrEnum):
    ENGLISH = "en"
    SINHALA = "si"


class InterviewStatus(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    COMPLETED = "completed"


class InterviewSession(Base):
    """A durable interview session and its lifecycle timestamps."""

    __tablename__ = "interview_sessions"
    __table_args__ = (
        CheckConstraint(
            "mode IN ('mock_interview', 'career_coach')",
            name="ck_interview_sessions_mode",
        ),
        CheckConstraint(
            "language IN ('en', 'si')",
            name="ck_interview_sessions_language",
        ),
        CheckConstraint(
            "status IN ('created', 'active', 'completed')",
            name="ck_interview_sessions_status",
        ),
        CheckConstraint(
            "(status = 'created' AND started_at IS NULL AND completed_at IS NULL) "
            "OR (status = 'active' AND started_at IS NOT NULL "
            "AND completed_at IS NULL) "
            "OR (status = 'completed' AND started_at IS NOT NULL "
            "AND completed_at IS NOT NULL)",
            name="ck_interview_sessions_lifecycle_timestamps",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_interview_sessions_timestamp_order",
        ),
        Index("ix_interview_sessions_status", "status"),
        Index("ix_interview_sessions_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    mode: Mapped[str] = mapped_column(String(32), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=InterviewStatus.CREATED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
