"""Test for creating interview sessions."""

import pytest
from httpx import ASGITransport, AsyncClient

from interview_service.main import app


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
