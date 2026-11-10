"""Typed request and response contracts for interview sessions."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict

from interview_service.models import (
    InterviewLanguage,
    InterviewMode,
    InterviewStatus,
)


class CreateInterviewRequest(BaseModel):
    mode: InterviewMode
    language: InterviewLanguage


class InterviewSessionResponse(BaseModel):
    """Stable public contract; persistence timestamps remain internal."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    mode: InterviewMode
    language: InterviewLanguage
    status: InterviewStatus
