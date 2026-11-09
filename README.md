# Bilingual Interview Coach

Foundation for two independently runnable FastAPI applications in one Python 3.12 uv project:

- Public API: `api/main.py`, served at `http://localhost:8000`
- Interview service: `interview_service/main.py`, served at `http://localhost:8001`

## Setup (PowerShell)

Install [uv](https://docs.astral.sh/uv/), then create the locked development environment:

```powershell
uv python install 3.12
uv sync --locked
```

## Run

Start each application in a separate PowerShell window:

```powershell
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
```

```powershell
uv run uvicorn interview_service.main:app --host 127.0.0.1 --port 8001
```

Health checks are available at `http://localhost:8000/health` and `http://localhost:8001/health`.

## Test and quality checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv audit
```

## Deferred scope

- **AUTH-001:** Add OAuth2/OIDC authentication and JWT validation.
- The first interview operation and its HTTP contract belong in a separate issue.

