"""Public API application entry point."""

import os

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


@app.post("/v1/interviews", status_code=201)
async def create_interview_session(payload: dict[str, str]) -> JSONResponse:
    try:
        async with create_interview_service_client() as client:
            response = await client.post("/v1/interviews", json=payload)
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

    if response.status_code not in {201, 422}:
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


@app.get("/v1/interviews/{session_id}")
async def get_interview_session(session_id: str) -> JSONResponse:
    try:
        async with create_interview_service_client() as client:
            response = await client.get(f"/v1/interviews/{session_id}")
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

    if response.status_code not in {200, 404}:
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
