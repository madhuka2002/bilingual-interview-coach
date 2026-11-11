"""Test interview session creation through the public API."""

import json
from collections.abc import Callable

import pytest
from httpx import (
    ASGITransport,
    AsyncClient,
    ConnectError,
    MockTransport,
    ReadTimeout,
    Request,
    Response,
)

from api import main as api_main

PAYLOAD = {"mode": "mock_interview", "language": "en"}
SESSION_ID = "11111111-1111-4111-8111-111111111111"


async def post_interview(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[Request], Response],
) -> Response:
    def fake_client() -> AsyncClient:
        return AsyncClient(
            transport=MockTransport(handler),
            base_url="http://interview-service",
        )

    monkeypatch.setattr(api_main, "create_interview_service_client", fake_client)

    transport = ASGITransport(app=api_main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/interviews", json=PAYLOAD)


async def get_interview(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[Request], Response],
    *,
    service_url: str = "http://interview-service",
) -> Response:
    def fake_client() -> AsyncClient:
        return AsyncClient(
            transport=MockTransport(handler),
            base_url=service_url,
        )

    monkeypatch.setattr(api_main, "create_interview_service_client", fake_client)

    transport = ASGITransport(app=api_main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(f"/v1/interviews/{SESSION_ID}")


async def post_lifecycle_action(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[Request], Response],
    action: str,
) -> Response:
    def fake_client() -> AsyncClient:
        return AsyncClient(
            transport=MockTransport(handler),
            base_url="http://interview-service",
        )

    monkeypatch.setattr(api_main, "create_interview_service_client", fake_client)

    transport = ASGITransport(app=api_main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(f"/v1/interviews/{SESSION_ID}/{action}")


@pytest.mark.anyio
async def test_public_api_creates_interview_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_reply = {
        "id": "11111111-1111-4111-8111-111111111111",
        **PAYLOAD,
        "status": "created",
    }

    def handle_service_request(request: Request) -> Response:
        assert request.method == "POST"
        assert request.url.path == "/v1/interviews"
        assert json.loads(request.content) == PAYLOAD
        return Response(201, json=service_reply)

    response = await post_interview(monkeypatch, handle_service_request)

    assert response.status_code == 201
    assert response.json() == service_reply


@pytest.mark.anyio
async def test_public_api_forwards_service_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_reply = {
        "detail": [
            {
                "type": "literal_error",
                "loc": ["body", "mode"],
                "msg": "Input should be 'mock_interview' or 'career_coach'",
                "input": "invalid",
            }
        ]
    }

    def handle_service_request(request: Request) -> Response:
        return Response(422, json=service_reply)

    response = await post_interview(monkeypatch, handle_service_request)

    assert response.status_code == 422
    assert response.json() == service_reply


@pytest.mark.anyio
async def test_public_api_returns_503_when_service_cannot_be_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handle_service_request(request: Request) -> Response:
        raise ConnectError("private connection details", request=request)

    response = await post_interview(monkeypatch, handle_service_request)

    assert response.status_code == 503
    assert response.json() == {"detail": "Interview service unavailable"}
    assert "private connection details" not in response.text


@pytest.mark.anyio
async def test_public_api_returns_504_when_service_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handle_service_request(request: Request) -> Response:
        raise ReadTimeout("private timeout details", request=request)

    response = await post_interview(monkeypatch, handle_service_request)

    assert response.status_code == 504
    assert response.json() == {"detail": "Interview service timed out"}
    assert "private timeout details" not in response.text


@pytest.mark.anyio
async def test_public_api_returns_502_for_unexpected_service_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handle_service_request(request: Request) -> Response:
        return Response(500, json={"detail": "private upstream details"})

    response = await post_interview(monkeypatch, handle_service_request)

    assert response.status_code == 502
    assert response.json() == {"detail": "Invalid response from interview service"}
    assert "private upstream details" not in response.text


@pytest.mark.anyio
async def test_public_api_returns_502_for_invalid_service_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handle_service_request(request: Request) -> Response:
        return Response(201, content=b"not valid JSON")

    response = await post_interview(monkeypatch, handle_service_request)

    assert response.status_code == 502
    assert response.json() == {"detail": "Invalid response from interview service"}


@pytest.mark.anyio
async def test_public_api_retrieves_interview_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_reply = {
        "id": SESSION_ID,
        **PAYLOAD,
        "status": "created",
    }

    def handle_service_request(request: Request) -> Response:
        return Response(200, json=service_reply)

    response = await get_interview(monkeypatch, handle_service_request)

    assert response.status_code == 200
    assert response.json() == service_reply


@pytest.mark.anyio
async def test_public_api_forwards_session_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_reply = {"detail": "Interview session not found"}

    def handle_service_request(request: Request) -> Response:
        return Response(404, json=service_reply)

    response = await get_interview(monkeypatch, handle_service_request)

    assert response.status_code == 404
    assert response.json() == service_reply


@pytest.mark.anyio
async def test_public_api_get_returns_503_when_service_cannot_be_reached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handle_service_request(request: Request) -> Response:
        raise ConnectError("private connection details", request=request)

    response = await get_interview(monkeypatch, handle_service_request)

    assert response.status_code == 503
    assert response.json() == {"detail": "Interview service unavailable"}
    assert "private connection details" not in response.text


@pytest.mark.anyio
async def test_public_api_get_returns_504_when_service_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handle_service_request(request: Request) -> Response:
        raise ReadTimeout("private timeout details", request=request)

    response = await get_interview(monkeypatch, handle_service_request)

    assert response.status_code == 504
    assert response.json() == {"detail": "Interview service timed out"}
    assert "private timeout details" not in response.text


@pytest.mark.anyio
async def test_public_api_get_returns_502_for_unexpected_service_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handle_service_request(request: Request) -> Response:
        return Response(500, json={"detail": "private upstream details"})

    response = await get_interview(monkeypatch, handle_service_request)

    assert response.status_code == 502
    assert response.json() == {"detail": "Invalid response from interview service"}
    assert "private upstream details" not in response.text


@pytest.mark.anyio
async def test_public_api_get_returns_502_for_invalid_service_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handle_service_request(request: Request) -> Response:
        return Response(200, content=b"not valid JSON")

    response = await get_interview(monkeypatch, handle_service_request)

    assert response.status_code == 502
    assert response.json() == {"detail": "Invalid response from interview service"}


@pytest.mark.anyio
async def test_public_api_get_forwards_configured_service_url_and_session_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service_url = "http://configured-interview-service:9000"

    def handle_service_request(request: Request) -> Response:
        assert request.method == "GET"
        assert str(request.url) == f"{service_url}/v1/interviews/{SESSION_ID}"
        return Response(200, json={"id": SESSION_ID})

    response = await get_interview(
        monkeypatch,
        handle_service_request,
        service_url=service_url,
    )

    assert response.status_code == 200


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("action", "service_status", "session_status"),
    [
        ("start", 200, "active"),
        ("complete", 200, "completed"),
    ],
)
async def test_public_api_forwards_lifecycle_actions(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    service_status: int,
    session_status: str,
) -> None:
    service_reply = {
        "id": SESSION_ID,
        **PAYLOAD,
        "status": session_status,
    }

    def handle_service_request(request: Request) -> Response:
        assert request.method == "POST"
        assert request.url.path == f"/v1/interviews/{SESSION_ID}/{action}"
        assert request.content == b""
        return Response(service_status, json=service_reply)

    response = await post_lifecycle_action(
        monkeypatch,
        handle_service_request,
        action,
    )

    assert response.status_code == service_status
    assert response.json() == service_reply


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("action", "service_status", "service_reply"),
    [
        ("start", 404, {"detail": "Interview session not found"}),
        (
            "complete",
            409,
            {"detail": "Cannot transition interview session from created to completed"},
        ),
    ],
)
async def test_public_api_forwards_lifecycle_errors(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    service_status: int,
    service_reply: dict[str, str],
) -> None:
    def handle_service_request(request: Request) -> Response:
        return Response(service_status, json=service_reply)

    response = await post_lifecycle_action(
        monkeypatch,
        handle_service_request,
        action,
    )

    assert response.status_code == service_status
    assert response.json() == service_reply


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("action", "failure", "expected_status", "expected_detail"),
    [
        ("start", "connection", 503, "Interview service unavailable"),
        ("complete", "timeout", 504, "Interview service timed out"),
        ("start", "status", 502, "Invalid response from interview service"),
        ("complete", "json", 502, "Invalid response from interview service"),
    ],
)
async def test_public_api_handles_lifecycle_downstream_failures(
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    failure: str,
    expected_status: int,
    expected_detail: str,
) -> None:
    def handle_service_request(request: Request) -> Response:
        if failure == "connection":
            raise ConnectError("private connection details", request=request)
        if failure == "timeout":
            raise ReadTimeout("private timeout details", request=request)
        if failure == "status":
            return Response(500, json={"detail": "private upstream details"})
        return Response(200, content=b"not valid JSON")

    response = await post_lifecycle_action(
        monkeypatch,
        handle_service_request,
        action,
    )

    assert response.status_code == expected_status
    assert response.json() == {"detail": expected_detail}
    assert "private" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("configured_url", "expected_url"),
    [
        (None, "http://127.0.0.1:8001"),
        ("http://interview-service:9000", "http://interview-service:9000"),
    ],
)
async def test_interview_service_client_configuration(
    monkeypatch: pytest.MonkeyPatch,
    configured_url: str | None,
    expected_url: str,
) -> None:
    if configured_url is None:
        monkeypatch.delenv("INTERVIEW_SERVICE_URL", raising=False)
    else:
        monkeypatch.setenv("INTERVIEW_SERVICE_URL", configured_url)

    async with api_main.create_interview_service_client() as client:
        assert str(client.base_url) == expected_url
        assert client.timeout.connect == api_main.INTERVIEW_SERVICE_TIMEOUT_SECONDS
        assert client.timeout.read == api_main.INTERVIEW_SERVICE_TIMEOUT_SECONDS
        assert client.timeout.write == api_main.INTERVIEW_SERVICE_TIMEOUT_SECONDS
        assert client.timeout.pool == api_main.INTERVIEW_SERVICE_TIMEOUT_SECONDS


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("method", "suffix", "service_status"),
    [
        ("GET", "current-question", 200),
        ("GET", "history", 200),
        ("GET", "feedback", 200),
        ("GET", "summary", 409),
        ("POST", "answers", 200),
    ],
)
async def test_public_api_forwards_interview_engine_routes(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    suffix: str,
    service_status: int,
) -> None:
    answer_payload = {"question_id": SESSION_ID, "text": "My answer"}

    def handler(request: Request) -> Response:
        assert request.method == method
        assert request.url.path == f"/v1/interviews/{SESSION_ID}/{suffix}"
        if suffix == "answers":
            assert json.loads(request.content) == answer_payload
        return Response(service_status, json={"route": suffix})

    def fake_client() -> AsyncClient:
        return AsyncClient(
            transport=MockTransport(handler),
            base_url="http://interview-service",
        )

    monkeypatch.setattr(api_main, "create_interview_service_client", fake_client)
    transport = ASGITransport(app=api_main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        if method == "POST":
            response = await client.post(
                f"/v1/interviews/{SESSION_ID}/{suffix}",
                json=answer_payload,
            )
        else:
            response = await client.get(f"/v1/interviews/{SESSION_ID}/{suffix}")

    assert response.status_code == service_status
    assert response.json() == {"route": suffix}


@pytest.mark.anyio
async def test_public_api_forwards_provider_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(request: Request) -> Response:
        return Response(504, json={"detail": "AI provider timed out"})

    response = await post_lifecycle_action(
        monkeypatch,
        handler,
        "start",
    )

    assert response.status_code == 504
    assert response.json() == {"detail": "AI provider timed out"}


@pytest.mark.anyio
async def test_public_api_forwards_configuration_payload_and_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_payload = {
        **PAYLOAD,
        "target_role": "Data Engineer",
        "experience_level": "senior",
        "category": "technical",
        "difficulty": "advanced",
        "question_limit": 3,
    }

    def handler(request: Request) -> Response:
        if request.method == "POST":
            assert json.loads(request.content) == configured_payload
            return Response(201, json={"id": SESSION_ID, "status": "created"})
        assert request.url.path == f"/v1/interviews/{SESSION_ID}/configuration"
        return Response(200, json={"target_role": "Data Engineer"})

    def fake_client() -> AsyncClient:
        return AsyncClient(
            transport=MockTransport(handler),
            base_url="http://interview-service",
        )

    monkeypatch.setattr(api_main, "create_interview_service_client", fake_client)
    transport = ASGITransport(app=api_main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/v1/interviews", json=configured_payload)
        config = await client.get(f"/v1/interviews/{SESSION_ID}/configuration")

    assert created.status_code == 201
    assert config.status_code == 200
    assert config.json() == {"target_role": "Data Engineer"}
