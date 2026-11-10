"""Interview service application entry point."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from interview_service.database import get_session
from interview_service.models import InterviewSession, InterviewStatus
from interview_service.schemas import CreateInterviewRequest, InterviewSessionResponse
from interview_service.services import (
    InvalidTransitionError,
    get_interview,
    transition_interview,
)

logger = logging.getLogger(__name__)
app = FastAPI(title="Bilingual Interview Coach Interview Service")
DatabaseSession = Annotated[Session, Depends(get_session)]


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


def apply_transition(
    database_session: Session,
    session_id: str,
    *,
    expected_status: InterviewStatus,
    target_status: InterviewStatus,
) -> InterviewSession:
    try:
        interview = transition_interview(
            database_session,
            parse_session_id(session_id),
            expected_status=expected_status,
            target_status=target_status,
        )
    except InvalidTransitionError as error:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Cannot transition interview session from "
                f"{error.current_status} to {error.requested_status}"
            ),
        ) from error
    if interview is None:
        raise HTTPException(status_code=404, detail="Interview session not found")
    return interview


@app.post(
    "/v1/interviews/{session_id}/start",
    response_model=InterviewSessionResponse,
)
def start_interview_session(
    session_id: str,
    database_session: DatabaseSession,
) -> InterviewSession:
    """Transition created to active; repeated starts are idempotent."""
    return apply_transition(
        database_session,
        session_id,
        expected_status=InterviewStatus.CREATED,
        target_status=InterviewStatus.ACTIVE,
    )


@app.post(
    "/v1/interviews/{session_id}/complete",
    response_model=InterviewSessionResponse,
)
def complete_interview_session(
    session_id: str,
    database_session: DatabaseSession,
) -> InterviewSession:
    """Transition active to completed; repeated completes are idempotent."""
    return apply_transition(
        database_session,
        session_id,
        expected_status=InterviewStatus.ACTIVE,
        target_status=InterviewStatus.COMPLETED,
    )
