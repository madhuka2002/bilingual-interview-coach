"""Interview service application entry point."""

from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="Bilingual Interview Coach Interview Service")
interview_sessions: dict[str, dict[str, str]] = {}


@app.get("/health")
async def health() -> dict[str, str]:
    """Report that the interview service process is healthy."""
    return {"status": "ok", "service": "interview-service"}


class CreateInterviewRequest(BaseModel):
    mode: Literal[
        "mock_interview", "career_coach"
    ]  # Only allow these two modes for now
    language: Literal["en", "si"]  # Only allow English and Sinhala for now


@app.post("/v1/interviews", status_code=201)
async def create_interview_session(
    payload: CreateInterviewRequest,
) -> dict[str, str]:
    session = {
        "id": str(uuid4()),
        "mode": payload.mode,
        "language": payload.language,
        "status": "created",
    }
    interview_sessions[session["id"]] = session
    return session


@app.get("/v1/interviews/{session_id}")
async def get_interview_session(session_id: str) -> dict[str, str]:
    try:
        return interview_sessions[session_id]
    except KeyError as error:
        raise HTTPException(
            status_code=404,
            detail="Interview session not found",
        ) from error
