"""Interview session persistence and lifecycle tests."""

import asyncio
from datetime import UTC
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from interview_service.database import get_session
from interview_service.main import app
from interview_service.models import InterviewSession

UNKNOWN_ID = "11111111-1111-4111-8111-111111111111"


@pytest.mark.parametrize(
    ("mode", "language"),
    [
        ("mock_interview", "en"),  # Valid mode and language
        ("career_coach", "si"),  # Valid mode and language
    ],
)
@pytest.mark.anyio
async def test_create_interview_session(mode: str, language: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"mode": mode, "language": language}
        response = await client.post("/v1/interviews", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "mode": payload["mode"],
        "language": payload["language"],
        "status": "created",
    }
    session_id = body["id"]
    assert str(UUID(session_id)) == session_id


@pytest.mark.anyio
async def test_created_interview_session_can_be_retrieved() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        create_response = await client.post(
            "/v1/interviews",
            json={"mode": "mock_interview", "language": "en"},
        )
        created_session = create_response.json()
        get_response = await client.get(
            f"/v1/interviews/{created_session['id']}",
        )

    assert create_response.status_code == 201
    assert get_response.status_code == 200
    assert get_response.json() == created_session


@pytest.mark.anyio
async def test_unknown_interview_session_returns_not_found() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/v1/interviews/{UNKNOWN_ID}",
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Interview session not found"}


@pytest.mark.anyio
async def test_create_interview_session_invalid_payload() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"mode": "mock_interview", "language": "fr"}  # Invalid language code
        response = await client.post("/v1/interviews", json=payload)

    assert response.status_code == 422  # Unprocessable Entity


@pytest.mark.anyio
async def test_create_interview_session_rejects_unsupported_mode() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"mode": "unknown", "language": "en"}  # Unsupported mode
        response = await client.post("/v1/interviews", json=payload)

    assert response.status_code == 422  # Unprocessable Entity


@pytest.mark.anyio
async def test_create_interview_session_rejects_missing_language() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {"mode": "mock_interview"}  # Missing language field
        response = await client.post("/v1/interviews", json=payload)

    assert response.status_code == 422  # Unprocessable Entity


@pytest.mark.anyio
async def test_session_persists_across_database_sessions(
    database_engine: Engine,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = (
            await client.post(
                "/v1/interviews",
                json={"mode": "mock_interview", "language": "en"},
            )
        ).json()

    session_factory = sessionmaker(bind=database_engine)
    with session_factory() as reopened_session:
        persisted = reopened_session.get(InterviewSession, UUID(created["id"]))

    assert persisted is not None
    assert persisted.mode == "mock_interview"
    assert persisted.language == "en"
    assert persisted.status == "created"
    assert persisted.created_at is not None
    assert persisted.updated_at is not None
    if database_engine.dialect.name == "postgresql":
        assert persisted.created_at.tzinfo is not None
        assert persisted.created_at.utcoffset() == UTC.utcoffset(None)


@pytest.mark.anyio
async def test_valid_lifecycle_and_idempotent_repeats(
    database_engine: Engine,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/v1/interviews",
            json={"mode": "career_coach", "language": "si"},
        )
        session_id = created.json()["id"]

        started = await client.post(f"/v1/interviews/{session_id}/start")
        repeated_start = await client.post(f"/v1/interviews/{session_id}/start")
        completed = await client.post(f"/v1/interviews/{session_id}/complete")
        repeated_complete = await client.post(f"/v1/interviews/{session_id}/complete")

    assert started.status_code == 200
    assert started.json()["status"] == "active"
    assert repeated_start.status_code == 200
    assert repeated_start.json() == started.json()
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert repeated_complete.status_code == 200
    assert repeated_complete.json() == completed.json()

    with Session(database_engine) as database_session:
        persisted = database_session.scalar(
            select(InterviewSession).where(InterviewSession.id == UUID(session_id))
        )
        assert persisted is not None
        assert persisted.started_at is not None
        assert persisted.completed_at is not None
        assert persisted.updated_at >= persisted.created_at
        assert persisted.completed_at >= persisted.started_at


@pytest.mark.anyio
async def test_complete_before_start_returns_conflict() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/v1/interviews",
            json={"mode": "mock_interview", "language": "en"},
        )
        session_id = created.json()["id"]
        response = await client.post(f"/v1/interviews/{session_id}/complete")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Cannot transition interview session from created to completed"
    }


@pytest.mark.anyio
async def test_start_after_completion_returns_conflict() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/v1/interviews",
            json={"mode": "mock_interview", "language": "en"},
        )
        session_id = created.json()["id"]
        await client.post(f"/v1/interviews/{session_id}/start")
        await client.post(f"/v1/interviews/{session_id}/complete")
        response = await client.post(f"/v1/interviews/{session_id}/start")

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Cannot transition interview session from completed to active"
    }


@pytest.mark.anyio
@pytest.mark.parametrize("action", ["start", "complete"])
async def test_unknown_session_lifecycle_returns_not_found(action: str) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/v1/interviews/{UNKNOWN_ID}/{action}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Interview session not found"}


@pytest.mark.anyio
async def test_malformed_session_id_returns_not_found() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/v1/interviews/not-a-uuid")

    assert response.status_code == 404
    assert response.json() == {"detail": "Interview session not found"}


@pytest.mark.anyio
async def test_concurrent_start_requests_are_safe() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/v1/interviews",
            json={"mode": "mock_interview", "language": "en"},
        )
        session_id = created.json()["id"]
        responses = await asyncio.gather(
            client.post(f"/v1/interviews/{session_id}/start"),
            client.post(f"/v1/interviews/{session_id}/start"),
        )

    assert [response.status_code for response in responses] == [200, 200]
    assert {response.json()["status"] for response in responses} == {"active"}


@pytest.mark.anyio
async def test_database_error_is_sanitized_and_rolls_back() -> None:
    database_session = MagicMock(spec=Session)
    database_session.flush.side_effect = OperationalError(
        "statement", {}, Exception("private database details")
    )

    def failing_session():
        try:
            yield database_session
        except BaseException:
            database_session.rollback()
            raise

    app.dependency_overrides[get_session] = failing_session
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/interviews",
            json={"mode": "mock_interview", "language": "en"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}
    assert "private database details" not in response.text
    database_session.rollback.assert_called_once()
