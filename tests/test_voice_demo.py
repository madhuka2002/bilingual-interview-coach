"""Public API voice forwarding and minimal demo tests."""

import pytest
from httpx import ASGITransport, AsyncClient, MockTransport, Request, Response

from api import main as api_main

SESSION_ID = "11111111-1111-4111-8111-111111111111"
pytestmark = pytest.mark.anyio


async def test_public_api_forwards_fixed_voice_token_route(monkeypatch) -> None:
    def handler(request: Request) -> Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/interviews/{SESSION_ID}/voice/token"
        assert request.content == b""
        return Response(
            200,
            json={
                "server_url": "ws://127.0.0.1:7880",
                "participant_token": "signed-token",
                "room_name": "bic-server-owned",
                "participant_identity": "candidate-server-owned",
                "expires_in": 600,
            },
        )

    def fake_client() -> AsyncClient:
        return AsyncClient(
            transport=MockTransport(handler), base_url="http://interview-service"
        )

    monkeypatch.setattr(api_main, "create_interview_service_client", fake_client)
    async with AsyncClient(
        transport=ASGITransport(app=api_main.app), base_url="http://test"
    ) as client:
        response = await client.post(f"/v1/interviews/{SESSION_ID}/voice/token")

    assert response.status_code == 200
    assert response.json()["room_name"] == "bic-server-owned"


async def test_voice_demo_contains_required_local_controls() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=api_main.app), base_url="http://test"
    ) as client:
        response = await client.get("/voice-demo")

    assert response.status_code == 200
    assert "Connect microphone" in response.text
    assert "Current question" in response.text
    assert "Connection" in response.text
    assert "livekit-client@2.23.0" in response.text
    assert "LIVEKIT_API_SECRET" not in response.text
