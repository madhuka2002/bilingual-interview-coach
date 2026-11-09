"""Interview service application entry point."""

from typing import Literal
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="Bilingual Interview Coach Interview Service")


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
    return {
        "id": str(uuid4()),
        "mode": payload.mode,
        "language": payload.language,
        "status": "created",
    }
