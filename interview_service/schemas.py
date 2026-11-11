"""Typed HTTP contracts for interview sessions and conversations."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from interview_service.models import (
    ExperienceLevel,
    InterviewCategory,
    InterviewDifficulty,
    InterviewLanguage,
    InterviewMode,
    InterviewStatus,
)


class CreateInterviewRequest(BaseModel):
    mode: InterviewMode
    language: InterviewLanguage
    target_role: str = Field(default="Software Engineer", min_length=2, max_length=120)
    experience_level: ExperienceLevel = ExperienceLevel.MID
    category: InterviewCategory = InterviewCategory.MIXED
    difficulty: InterviewDifficulty = InterviewDifficulty.INTERMEDIATE
    question_limit: int | None = Field(default=None, ge=1, le=20)

    @field_validator("target_role")
    @classmethod
    def role_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("target role must not be blank")
        return value


class InterviewSessionResponse(BaseModel):
    """Stable public contract; persistence timestamps remain internal."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mode: InterviewMode
    language: InterviewLanguage
    status: InterviewStatus


class InterviewConfigurationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    interview_id: UUID
    target_role: str
    experience_level: ExperienceLevel
    category: InterviewCategory
    difficulty: InterviewDifficulty
    preferred_language: InterviewLanguage
    question_limit: int


class QuestionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    sequence: int
    text: str
    topic: str
    provider: str
    model: str
    created_at: datetime


class SubmitAnswerRequest(BaseModel):
    question_id: UUID
    text: str = Field(min_length=1, max_length=20_000)

    @field_validator("text")
    @classmethod
    def answer_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("answer text must not be blank")
        return value


class AnswerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    question_id: UUID
    text: str
    created_at: datetime


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    answer_id: UUID
    score: int
    feedback: str
    strengths: list[str]
    improvements: list[str]
    criteria: dict[str, int]
    learning_areas: list[str]
    provider: str
    model: str
    created_at: datetime


class SummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    interview_id: UUID
    overall_score: int
    summary: str
    strengths: list[str]
    improvements: list[str]
    provider: str
    model: str
    created_at: datetime


class SubmitAnswerResponse(BaseModel):
    answer: AnswerResponse
    evaluation: EvaluationResponse
    next_question: QuestionResponse | None
    completed: bool


class HistoryItemResponse(BaseModel):
    question: QuestionResponse
    answer: AnswerResponse | None
    evaluation: EvaluationResponse | None


class InterviewHistoryResponse(BaseModel):
    interview: InterviewSessionResponse
    items: list[HistoryItemResponse]


class InterviewFeedbackResponse(BaseModel):
    interview_id: UUID
    evaluations: list[EvaluationResponse]
