"""End-to-end text interview engine tests with deterministic providers."""

from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from interview_service.ai.base import (
    AIProviderResponseError,
    AIProviderTimeoutError,
    ConversationTurn,
    QuestionResult,
)
from interview_service.ai.config import get_ai_provider
from interview_service.ai.mock import MockAIProvider
from interview_service.main import app
from interview_service.models import (
    CandidateAnswer,
    InterviewQuestion,
    InterviewSession,
)


async def create_interview(client: AsyncClient) -> dict:
    response = await client.post(
        "/v1/interviews",
        json={"mode": "mock_interview", "language": "en"},
    )
    assert response.status_code == 201
    return response.json()


async def start_interview(client: AsyncClient, session_id: str) -> dict:
    response = await client.post(f"/v1/interviews/{session_id}/start")
    assert response.status_code == 200
    return response.json()


@pytest.mark.anyio
async def test_first_question_answer_feedback_and_next_question_persist(
    database_engine: Engine,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        interview = await create_interview(client)
        await start_interview(client, interview["id"])
        first = await client.get(f"/v1/interviews/{interview['id']}/current-question")
        submitted = await client.post(
            f"/v1/interviews/{interview['id']}/answers",
            json={
                "question_id": first.json()["id"],
                "text": "I led a migration that reduced deployment time by half.",
            },
        )
        history = await client.get(f"/v1/interviews/{interview['id']}/history")
        feedback = await client.get(f"/v1/interviews/{interview['id']}/feedback")

    assert first.status_code == 200
    assert first.json()["sequence"] == 1
    assert submitted.status_code == 200
    assert submitted.json()["evaluation"]["score"] > 0
    assert submitted.json()["next_question"]["sequence"] == 2
    assert submitted.json()["completed"] is False
    assert len(history.json()["items"]) == 2
    assert history.json()["items"][0]["answer"]["text"].startswith("I led")
    assert history.json()["items"][1]["answer"] is None
    assert len(feedback.json()["evaluations"]) == 1

    with Session(database_engine) as session:
        questions = session.scalars(
            select(InterviewQuestion).order_by(InterviewQuestion.sequence)
        ).all()
        assert [question.sequence for question in questions] == [1, 2]
        assert session.scalar(select(CandidateAnswer)) is not None


@pytest.mark.anyio
async def test_duplicate_answer_is_rejected() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        interview = await create_interview(client)
        await start_interview(client, interview["id"])
        question = (
            await client.get(f"/v1/interviews/{interview['id']}/current-question")
        ).json()
        payload = {"question_id": question["id"], "text": "A useful answer."}
        first = await client.post(
            f"/v1/interviews/{interview['id']}/answers", json=payload
        )
        duplicate = await client.post(
            f"/v1/interviews/{interview['id']}/answers", json=payload
        )

    assert first.status_code == 200
    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "An answer has already been submitted"}


@pytest.mark.anyio
async def test_created_session_has_no_current_question_or_summary() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        interview = await create_interview(client)
        current = await client.get(f"/v1/interviews/{interview['id']}/current-question")
        summary = await client.get(f"/v1/interviews/{interview['id']}/summary")

    assert current.status_code == 409
    assert summary.status_code == 409


@pytest.mark.anyio
async def test_question_limit_completes_and_generates_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_QUESTION_LIMIT", "1")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        interview = await create_interview(client)
        await start_interview(client, interview["id"])
        question = (
            await client.get(f"/v1/interviews/{interview['id']}/current-question")
        ).json()
        submitted = await client.post(
            f"/v1/interviews/{interview['id']}/answers",
            json={"question_id": question["id"], "text": "A final answer."},
        )
        summary = await client.get(f"/v1/interviews/{interview['id']}/summary")
        session = await client.get(f"/v1/interviews/{interview['id']}")

    assert submitted.status_code == 200
    assert submitted.json()["completed"] is True
    assert submitted.json()["next_question"] is None
    assert summary.status_code == 200
    assert summary.json()["interview_id"] == interview["id"]
    assert session.json()["status"] == "completed"


class TimeoutProvider(MockAIProvider):
    def generate_question(
        self,
        *,
        mode: str,
        language: str,
        sequence: int,
        history: list[ConversationTurn],
    ) -> QuestionResult:
        raise AIProviderTimeoutError("private timeout details")


class FailNextQuestionProvider(MockAIProvider):
    def generate_question(
        self,
        *,
        mode: str,
        language: str,
        sequence: int,
        history: list[ConversationTurn],
    ) -> QuestionResult:
        if sequence == 2:
            raise AIProviderResponseError("private malformed details")
        return super().generate_question(
            mode=mode,
            language=language,
            sequence=sequence,
            history=history,
        )


@pytest.mark.anyio
async def test_first_question_timeout_leaves_session_created(
    database_engine: Engine,
) -> None:
    app.dependency_overrides[get_ai_provider] = TimeoutProvider
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        interview = await create_interview(client)
        failed = await client.post(f"/v1/interviews/{interview['id']}/start")
        retrieved = await client.get(f"/v1/interviews/{interview['id']}")

    assert failed.status_code == 504
    assert failed.json() == {"detail": "AI provider timed out"}
    assert "private" not in failed.text
    assert retrieved.json()["status"] == "created"
    with Session(database_engine) as session:
        assert session.scalar(select(InterviewQuestion)) is None


@pytest.mark.anyio
async def test_failed_next_question_rolls_back_entire_answer_cycle(
    database_engine: Engine,
) -> None:
    app.dependency_overrides[get_ai_provider] = FailNextQuestionProvider
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        interview = await create_interview(client)
        await start_interview(client, interview["id"])
        question = (
            await client.get(f"/v1/interviews/{interview['id']}/current-question")
        ).json()
        failed = await client.post(
            f"/v1/interviews/{interview['id']}/answers",
            json={"question_id": question["id"], "text": "Should roll back."},
        )
        history = await client.get(f"/v1/interviews/{interview['id']}/history")

    assert failed.status_code == 502
    assert failed.json() == {"detail": "Invalid AI provider response"}
    assert history.json()["items"][0]["answer"] is None
    with Session(database_engine) as session:
        assert session.scalar(select(CandidateAnswer)) is None
        persisted = session.get(InterviewSession, UUID(interview["id"]))
        assert persisted is not None and persisted.status == "active"
