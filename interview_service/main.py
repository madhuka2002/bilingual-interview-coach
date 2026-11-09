"""Interview service application entry point."""

from fastapi import FastAPI

app = FastAPI(title="Bilingual Interview Coach Interview Service")


@app.get("/health")
async def health() -> dict[str, str]:
    """Report that the interview service process is healthy."""
    return {"status": "ok", "service": "interview-service"}
