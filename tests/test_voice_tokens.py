"""Room binding and least-privilege LiveKit token tests."""

import time

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from interview_service.main import app
from interview_service.models import VoiceRoom


@pytest.fixture
def livekit_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVEKIT_URL", "ws://127.0.0.1:7880")
    monkeypatch.setenv("LIVEKIT_API_KEY", "test-key")
    monkeypatch.setenv("LIVEKIT_API_SECRET", "test-secret-at-least-thirty-two-bytes")
    monkeypatch.setenv("LIVEKIT_AGENT_NAME", "bic-test-agent")
    monkeypatch.setenv("LIVEKIT_TOKEN_TTL_SECONDS", "300")


@pytest.mark.anyio
async def test_candidate_token_is_bound_short_lived_and_least_privilege(
    livekit_environment: None,
    database_engine: Engine,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post(
            "/v1/interviews",
            json={"mode": "mock_interview", "language": "en"},
        )
        interview_id = created.json()["id"]
        response = await client.post(
            f"/v1/interviews/{interview_id}/voice/token",
            json={"room_name": "attacker-room", "identity": "attacker"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["server_url"] == "ws://127.0.0.1:7880"
    assert body["room_name"].startswith("bic-")
    assert body["room_name"] != "attacker-room"
    assert body["participant_identity"].startswith("candidate-")
    assert body["participant_identity"] != "attacker"
    claims = jwt.decode(
        body["participant_token"],
        "test-secret-at-least-thirty-two-bytes",
        algorithms=["HS256"],
    )
    assert claims["sub"] == body["participant_identity"]
    assert claims["exp"] - int(time.time()) <= 300
    assert claims["video"] == {
        "roomAdmin": False,
        "roomJoin": True,
        "room": body["room_name"],
        "canPublish": True,
        "canSubscribe": True,
        "canPublishData": False,
        "canPublishSources": ["microphone"],
        "canUpdateOwnMetadata": False,
    }
    assert claims.get("kind") != "agent"
    assert claims["roomConfig"]["agents"][0]["agentName"] == "bic-test-agent"
    with Session(database_engine) as session:
        persisted = session.scalar(select(VoiceRoom))
        assert persisted is not None
        assert persisted.room_name == body["room_name"]


@pytest.mark.anyio
async def test_reissued_token_reuses_server_owned_binding(
    livekit_environment: None,
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        interview_id = (
            await client.post(
                "/v1/interviews",
                json={"mode": "mock_interview", "language": "en"},
            )
        ).json()["id"]
        first = (await client.post(f"/v1/interviews/{interview_id}/voice/token")).json()
        second = (
            await client.post(f"/v1/interviews/{interview_id}/voice/token")
        ).json()

    assert first["room_name"] == second["room_name"]
    assert first["participant_identity"] == second["participant_identity"]


@pytest.mark.anyio
async def test_token_endpoint_sanitizes_missing_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"):
        monkeypatch.delenv(name, raising=False)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        interview_id = (
            await client.post(
                "/v1/interviews",
                json={"mode": "mock_interview", "language": "en"},
            )
        ).json()["id"]
        response = await client.post(f"/v1/interviews/{interview_id}/voice/token")

    assert response.status_code == 503
    assert response.json() == {"detail": "Voice service is not configured"}
    assert "LIVEKIT_API_SECRET" not in response.text
