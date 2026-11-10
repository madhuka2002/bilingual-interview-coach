"""Public API application entry point."""

import os
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import AsyncClient, RequestError, TimeoutException

app = FastAPI(title="Bilingual Interview Coach API")

DEFAULT_INTERVIEW_SERVICE_URL = "http://127.0.0.1:8001"
INTERVIEW_SERVICE_TIMEOUT_SECONDS = 5.0


@app.get("/health")
async def health() -> dict[str, str]:
    """Report that the public API process is healthy."""
    return {"status": "ok", "service": "api"}


def create_interview_service_client() -> AsyncClient:
    return AsyncClient(
        base_url=os.getenv("INTERVIEW_SERVICE_URL", DEFAULT_INTERVIEW_SERVICE_URL),
        timeout=INTERVIEW_SERVICE_TIMEOUT_SECONDS,
    )


async def forward_interview_request(
    method: str,
    path: str,
    *,
    allowed_statuses: set[int],
    json: dict[str, Any] | None = None,
) -> JSONResponse:
    """Forward a request while normalizing service-boundary failures."""
    try:
        async with create_interview_service_client() as client:
            response = await client.request(method, path, json=json)
    except TimeoutException:
        return JSONResponse(
            status_code=504,
            content={"detail": "Interview service timed out"},
        )
    except RequestError:
        return JSONResponse(
            status_code=503,
            content={"detail": "Interview service unavailable"},
        )

    if response.status_code not in allowed_statuses:
        return JSONResponse(
            status_code=502,
            content={"detail": "Invalid response from interview service"},
        )

    try:
        response_content = response.json()
    except ValueError:
        return JSONResponse(
            status_code=502,
            content={"detail": "Invalid response from interview service"},
        )

    return JSONResponse(status_code=response.status_code, content=response_content)


@app.post("/v1/interviews", status_code=201)
async def create_interview_session(payload: dict[str, str]) -> JSONResponse:
    return await forward_interview_request(
        "POST",
        "/v1/interviews",
        allowed_statuses={201, 422},
        json=payload,
    )


@app.get("/v1/interviews/{session_id}")
async def get_interview_session(session_id: str) -> JSONResponse:
    return await forward_interview_request(
        "GET",
        f"/v1/interviews/{session_id}",
        allowed_statuses={200, 404},
    )


@app.post("/v1/interviews/{session_id}/start")
async def start_interview_session(session_id: str) -> JSONResponse:
    return await forward_interview_request(
        "POST",
        f"/v1/interviews/{session_id}/start",
        allowed_statuses={200, 404, 409},
    )


@app.post("/v1/interviews/{session_id}/complete")
async def complete_interview_session(session_id: str) -> JSONResponse:
    return await forward_interview_request(
        "POST",
        f"/v1/interviews/{session_id}/complete",
        allowed_statuses={200, 404, 409},
    )
