"""Interview service application entry point."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from interview_service.ai.base import (
    AIProvider,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
)
from interview_service.ai.config import get_ai_provider, get_question_limit
from interview_service.database import get_session
from interview_service.engine import (
    InterviewConflictError,
    complete_interview,
    current_question,
    get_history,
    start_interview,
    submit_answer,
)
from interview_service.models import InterviewSession, InterviewStatus
from interview_service.schemas import (
    CreateInterviewRequest,
    EvaluationResponse,
    HistoryItemResponse,
    InterviewFeedbackResponse,
    InterviewHistoryResponse,
    InterviewSessionResponse,
    QuestionResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
    SummaryResponse,
)
from interview_service.services import get_interview

logger = logging.getLogger(__name__)
app = FastAPI(title="Bilingual Interview Coach Interview Service")
DatabaseSession = Annotated[Session, Depends(get_session)]
Provider = Annotated[AIProvider, Depends(get_ai_provider)]


@app.exception_handler(SQLAlchemyError)
async def handle_database_error(
    request: Request,
    error: SQLAlchemyError,
) -> JSONResponse:
    """Return a stable response without exposing database internals."""
    logger.exception(
        "Database operation failed for %s",
        request.url.path,
        exc_info=error,
    )
    return JSONResponse(status_code=503, content={"detail": "Database unavailable"})


@app.exception_handler(AIProviderTimeoutError)
async def handle_provider_timeout(
    request: Request,
    error: AIProviderTimeoutError,
) -> JSONResponse:
    logger.warning("AI provider timed out for %s: %s", request.url.path, error)
    return JSONResponse(status_code=504, content={"detail": "AI provider timed out"})


@app.exception_handler(AIProviderUnavailableError)
async def handle_provider_unavailable(
    request: Request,
    error: AIProviderUnavailableError,
) -> JSONResponse:
    logger.warning("AI provider unavailable for %s: %s", request.url.path, error)
    return JSONResponse(status_code=503, content={"detail": "AI provider unavailable"})


@app.exception_handler(AIProviderResponseError)
async def handle_provider_response_error(
    request: Request,
    error: AIProviderResponseError,
) -> JSONResponse:
    logger.warning("Invalid AI provider response for %s: %s", request.url.path, error)
    return JSONResponse(
        status_code=502, content={"detail": "Invalid AI provider response"}
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Report that the interview service process is healthy."""
    return {"status": "ok", "service": "interview-service"}


def parse_session_id(session_id: str) -> UUID:
    try:
        return UUID(session_id)
    except ValueError as error:
        raise HTTPException(
            status_code=404,
            detail="Interview session not found",
        ) from error


def require_interview(
    database_session: Session,
    session_id: str,
) -> InterviewSession:
    interview = get_interview(database_session, parse_session_id(session_id))
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return interview


@app.post(
    "/v1/interviews",
    status_code=201,
    response_model=InterviewSessionResponse,
)
def create_interview_session(
    payload: CreateInterviewRequest,
    database_session: DatabaseSession,
) -> InterviewSession:
    interview = InterviewSession(
        mode=payload.mode,
        language=payload.language,
        status=InterviewStatus.CREATED,
        max_questions=get_question_limit(),
    )
    database_session.add(interview)
    database_session.flush()
    return interview


@app.get(
    "/v1/interviews/{session_id}",
    response_model=InterviewSessionResponse,
)
def get_interview_session(
    session_id: str,
    database_session: DatabaseSession,
) -> InterviewSession:
    return require_interview(database_session, session_id)


@app.post(
    "/v1/interviews/{session_id}/start",
    response_model=InterviewSessionResponse,
)
def start_interview_session(
    session_id: str,
    database_session: DatabaseSession,
    provider: Provider,
) -> InterviewSession:
    """Generate the first question and transition created to active."""
    try:
        interview = start_interview(
            database_session,
            parse_session_id(session_id),
            provider,
        )
    except InterviewConflictError as error:
        raise HTTPException(status_code=409, detail=error.detail) from error
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return interview


@app.post(
    "/v1/interviews/{session_id}/complete",
    response_model=InterviewSessionResponse,
)
def complete_interview_session(
    session_id: str,
    database_session: DatabaseSession,
    provider: Provider,
) -> InterviewSession:
    """Generate final feedback and complete; repeated completes are idempotent."""
    try:
        interview = complete_interview(
            database_session,
            parse_session_id(session_id),
            provider,
        )
    except InterviewConflictError as error:
        raise HTTPException(status_code=409, detail=error.detail) from error
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return interview


@app.get(
    "/v1/interviews/{session_id}/current-question",
    response_model=QuestionResponse,
)
def get_current_question(
    session_id: str,
    database_session: DatabaseSession,
):
    try:
        interview, question = current_question(
            database_session,
            parse_session_id(session_id),
        )
    except InterviewConflictError as error:
        raise HTTPException(status_code=409, detail=error.detail) from error
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return question


@app.post(
    "/v1/interviews/{session_id}/answers",
    response_model=SubmitAnswerResponse,
)
def submit_interview_answer(
    session_id: str,
    payload: SubmitAnswerRequest,
    database_session: DatabaseSession,
    provider: Provider,
) -> SubmitAnswerResponse:
    try:
        result = submit_answer(
            database_session,
            parse_session_id(session_id),
            payload.question_id,
            payload.text,
            provider,
        )
    except InterviewConflictError as error:
        raise HTTPException(status_code=409, detail=error.detail) from error
    if result is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return SubmitAnswerResponse(
        answer=result.answer,
        evaluation=result.evaluation,
        next_question=result.next_question,
        completed=result.completed,
    )


@app.get(
    "/v1/interviews/{session_id}/history",
    response_model=InterviewHistoryResponse,
)
def get_interview_history(
    session_id: str,
    database_session: DatabaseSession,
) -> InterviewHistoryResponse:
    interview = get_history(database_session, parse_session_id(session_id))
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return InterviewHistoryResponse(
        interview=interview,
        items=[
            HistoryItemResponse(
                question=question,
                answer=question.answer,
                evaluation=question.answer.evaluation if question.answer else None,
            )
            for question in interview.questions
        ],
    )


@app.get(
    "/v1/interviews/{session_id}/feedback",
    response_model=InterviewFeedbackResponse,
)
def get_interview_feedback(
    session_id: str,
    database_session: DatabaseSession,
) -> InterviewFeedbackResponse:
    interview = get_history(database_session, parse_session_id(session_id))
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    evaluations = [
        question.answer.evaluation
        for question in interview.questions
        if question.answer and question.answer.evaluation
    ]
    return InterviewFeedbackResponse(
        interview_id=interview.id,
        evaluations=[EvaluationResponse.model_validate(item) for item in evaluations],
    )


@app.get(
    "/v1/interviews/{session_id}/summary",
    response_model=SummaryResponse,
)
def get_interview_summary(
    session_id: str,
    database_session: DatabaseSession,
):
    interview = get_history(database_session, parse_session_id(session_id))
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    if interview.status != InterviewStatus.COMPLETED or interview.summary is None:
        raise HTTPException(
            status_code=409, detail="Interview summary is not available"
        )
    return interview.summary
