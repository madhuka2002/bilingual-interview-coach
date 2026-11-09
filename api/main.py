"""Public API application entry point."""

from fastapi import FastAPI

app = FastAPI(title="Bilingual Interview Coach API")


@app.get("/health")
async def health() -> dict[str, str]:
    """Report that the public API process is healthy."""
    return {"status": "ok", "service": "api"}
