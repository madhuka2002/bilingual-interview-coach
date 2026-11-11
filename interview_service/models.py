"""SQLAlchemy models for persistent interview data."""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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


class ExperienceLevel(StrEnum):
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"


class InterviewCategory(StrEnum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    HR = "hr"
    MIXED = "mixed"


class InterviewDifficulty(StrEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


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
        CheckConstraint(
            "max_questions >= 1 AND max_questions <= 20",
            name="ck_interview_sessions_max_questions",
        ),
        CheckConstraint(
            "experience_level IN ('entry', 'mid', 'senior')",
            name="ck_interview_sessions_experience_level",
        ),
        CheckConstraint(
            "category IN ('technical', 'behavioral', 'hr', 'mixed')",
            name="ck_interview_sessions_category",
        ),
        CheckConstraint(
            "difficulty IN ('beginner', 'intermediate', 'advanced')",
            name="ck_interview_sessions_difficulty",
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
    max_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    target_role: Mapped[str] = mapped_column(
        String(120), nullable=False, default="Software Engineer"
    )
    experience_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ExperienceLevel.MID
    )
    category: Mapped[str] = mapped_column(
        String(16), nullable=False, default=InterviewCategory.MIXED
    )
    difficulty: Mapped[str] = mapped_column(
        String(16), nullable=False, default=InterviewDifficulty.INTERMEDIATE
    )
    questions: Mapped[list["InterviewQuestion"]] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
        order_by="InterviewQuestion.sequence",
    )
    summary: Mapped["InterviewSummary | None"] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
        uselist=False,
    )
    voice_room: Mapped["VoiceRoom | None"] = relationship(
        back_populates="interview",
        cascade="all, delete-orphan",
        uselist=False,
    )


class InterviewQuestion(Base):
    """An ordered, provider-generated question in an interview."""

    __tablename__ = "interview_questions"
    __table_args__ = (
        UniqueConstraint(
            "interview_id",
            "sequence",
            name="uq_interview_questions_interview_sequence",
        ),
        CheckConstraint("sequence >= 1", name="ck_interview_questions_sequence"),
        Index("ix_interview_questions_interview_id", "interview_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    topic: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    interview: Mapped[InterviewSession] = relationship(back_populates="questions")
    answer: Mapped["CandidateAnswer | None"] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        uselist=False,
    )


class CandidateAnswer(Base):
    """A candidate's single answer to an interview question."""

    __tablename__ = "candidate_answers"
    __table_args__ = (
        UniqueConstraint("question_id", name="uq_candidate_answers_question_id"),
        Index("ix_candidate_answers_question_id", "question_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    question: Mapped[InterviewQuestion] = relationship(back_populates="answer")
    evaluation: Mapped["AnswerEvaluation | None"] = relationship(
        back_populates="answer",
        cascade="all, delete-orphan",
        uselist=False,
    )


class AnswerEvaluation(Base):
    """Structured AI feedback for exactly one candidate answer."""

    __tablename__ = "answer_evaluations"
    __table_args__ = (
        UniqueConstraint("answer_id", name="uq_answer_evaluations_answer_id"),
        CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_answer_evaluations_score",
        ),
        Index("ix_answer_evaluations_answer_id", "answer_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    answer_id: Mapped[UUID] = mapped_column(
        ForeignKey("candidate_answers.id", ondelete="CASCADE"),
        nullable=False,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    strengths: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    improvements: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    criteria: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    learning_areas: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    answer: Mapped[CandidateAnswer] = relationship(back_populates="evaluation")


class InterviewSummary(Base):
    """Final provider-generated feedback for a completed interview."""

    __tablename__ = "interview_summaries"
    __table_args__ = (
        UniqueConstraint("interview_id", name="uq_interview_summaries_interview_id"),
        CheckConstraint(
            "overall_score >= 0 AND overall_score <= 100",
            name="ck_interview_summaries_overall_score",
        ),
        Index("ix_interview_summaries_interview_id", "interview_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    strengths: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    improvements: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    interview: Mapped[InterviewSession] = relationship(back_populates="summary")


class VoiceRoom(Base):
    """Server-owned LiveKit room binding for one durable interview."""

    __tablename__ = "voice_rooms"
    __table_args__ = (
        UniqueConstraint("interview_id", name="uq_voice_rooms_interview_id"),
        UniqueConstraint("room_name", name="uq_voice_rooms_room_name"),
        UniqueConstraint(
            "candidate_identity", name="uq_voice_rooms_candidate_identity"
        ),
        Index("ix_voice_rooms_interview_id", "interview_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    interview_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False
    )
    room_name: Mapped[str] = mapped_column(String(80), nullable=False)
    candidate_identity: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_connected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    interview: Mapped[InterviewSession] = relationship(back_populates="voice_room")
    transcripts: Mapped[list["VoiceTranscript"]] = relationship(
        back_populates="voice_room", cascade="all, delete-orphan"
    )


class VoiceTranscript(Base):
    """A finalized STT event submitted through the voice transport."""

    __tablename__ = "voice_transcripts"
    __table_args__ = (
        UniqueConstraint(
            "voice_room_id", "event_id", name="uq_voice_transcripts_room_event"
        ),
        UniqueConstraint("question_id", name="uq_voice_transcripts_question_id"),
        CheckConstraint(
            "status IN ('received', 'processed')",
            name="ck_voice_transcripts_status",
        ),
        Index("ix_voice_transcripts_voice_room_id", "voice_room_id"),
        Index("ix_voice_transcripts_question_id", "question_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    voice_room_id: Mapped[UUID] = mapped_column(
        ForeignKey("voice_rooms.id", ondelete="CASCADE"), nullable=False
    )
    question_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_questions.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    participant_identity: Mapped[str] = mapped_column(String(80), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="received")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    voice_room: Mapped[VoiceRoom] = relationship(back_populates="transcripts")
