"""Test for creating interview sessions."""

import pytest
from httpx import ASGITransport, AsyncClient

from interview_service.main import app, interview_sessions


@pytest.fixture(autouse=True)
def isolate_interview_sessions() -> None:
    interview_sessions.clear()
    yield
    interview_sessions.clear()


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
    assert body["mode"] == payload["mode"]
    session_id = body["id"]
    assert isinstance(session_id, str)
    assert session_id


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
            "/v1/interviews/11111111-1111-4111-8111-111111111111",
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
    assert interview_sessions == {}


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
