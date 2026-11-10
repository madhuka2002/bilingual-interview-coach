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
