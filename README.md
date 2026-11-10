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

### Start the database

Copy the environment template and replace the local-only password, then start
PostgreSQL 17 and apply migrations:

```powershell
Copy-Item .env.example .env
# Edit .env, then load DATABASE_URL into the current shell.
docker compose up -d postgres
$env:DATABASE_URL = (Get-Content .env | Where-Object { $_ -like 'DATABASE_URL=*' }) -replace '^DATABASE_URL=', ''
uv run alembic upgrade head
```

PostgreSQL listens on `127.0.0.1:5433` by default to avoid the conventional
local port. Change `BIC_POSTGRES_PORT` and the URL together if needed. Check it
with `docker compose ps`; stop it without deleting data using
`docker compose down`.

To intentionally reset local development data, first stop the service, then
explicitly remove the project volume:

```powershell
docker compose down
docker volume rm bilingual-interview-coach_postgres_data
docker compose up -d postgres
uv run alembic upgrade head
```

The application never removes volumes automatically. Do not point destructive
tests at this development database.

### Start the services

Start each application in a separate PowerShell window:

```powershell
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
```

```powershell
uv run uvicorn interview_service.main:app --host 127.0.0.1 --port 8001
```

Health checks are available at `http://localhost:8000/health` and `http://localhost:8001/health`.

Interview sessions follow `created -> active -> completed`. `start` is
idempotent for an active session and `complete` is idempotent for a completed
session; other invalid transitions return HTTP 409.

- `POST /v1/interviews`
- `GET /v1/interviews/{session_id}`
- `POST /v1/interviews/{session_id}/start`
- `POST /v1/interviews/{session_id}/complete`

## Test and quality checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv audit --locked
```

The default suite creates a fresh temporary SQLite database for each test. To
exercise the same persistence and concurrency tests against PostgreSQL, provide
an isolated database whose name ends in `_test`:

```powershell
$env:TEST_DATABASE_URL = 'postgresql+psycopg://user:password@127.0.0.1:5432/bic_test'
uv run --locked pytest
```

The test guard refuses destructive setup for PostgreSQL database names without
the `_test` suffix. Jenkins needs no database service for the default suite;
PostgreSQL integration can be enabled on an agent by supplying that variable
with an isolated test database.

## Deferred scope

- **AUTH-001:** Add OAuth2/OIDC authentication and JWT validation.
- The first interview operation and its HTTP contract belong in a separate issue.

