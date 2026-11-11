"""Provider-neutral contracts for interview AI operations."""

from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class QuestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=2000)
    topic: str = Field(min_length=1, max_length=120)


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100)
    feedback: str = Field(min_length=1, max_length=4000)
    strengths: list[str] = Field(min_length=1, max_length=10)
    improvements: list[str] = Field(min_length=1, max_length=10)


class SummaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    overall_score: int = Field(ge=0, le=100)
    summary: str = Field(min_length=1, max_length=6000)
    strengths: list[str] = Field(min_length=1, max_length=10)
    improvements: list[str] = Field(min_length=1, max_length=10)


@dataclass(frozen=True)
class ConversationTurn:
    sequence: int
    question: str
    answer: str | None = None
    score: int | None = None
    feedback: str | None = None


class AIProviderError(Exception):
    """Base class for sanitized provider failures."""


class AIProviderTimeoutError(AIProviderError):
    """The provider exceeded its configured deadline."""


class AIProviderUnavailableError(AIProviderError):
    """The provider is unreachable or not configured."""


class AIProviderResponseError(AIProviderError):
    """The provider failed or returned an unusable response."""


class AIProvider(Protocol):
    name: str
    model: str

    def generate_question(
        self,
        *,
        mode: str,
        language: str,
        sequence: int,
        history: list[ConversationTurn],
    ) -> QuestionResult: ...

    def evaluate_answer(
        self,
        *,
        mode: str,
        language: str,
        question: str,
        answer: str,
        history: list[ConversationTurn],
    ) -> EvaluationResult: ...

    def summarize_interview(
        self,
        *,
        mode: str,
        language: str,
        history: list[ConversationTurn],
    ) -> SummaryResult: ...
