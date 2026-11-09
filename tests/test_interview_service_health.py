"""Health checks for the interview service."""

import pytest
from httpx import ASGITransport, AsyncClient

from interview_service.main import app


@pytest.mark.anyio
async def test_health() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "interview-service"}
