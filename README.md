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

Interview sessions follow `created -> active -> completed`. Starting generates
the first text question. Answer submission evaluates the answer and atomically
creates either the next question or a final summary at the session's stored
question limit. `start` is idempotent for an active session and `complete` is
idempotent for a completed session; other invalid transitions return HTTP 409.

- `POST /v1/interviews`
- `GET /v1/interviews/{session_id}`
- `GET /v1/interviews/{session_id}/configuration`
- `POST /v1/interviews/{session_id}/start`
- `POST /v1/interviews/{session_id}/complete`
- `GET /v1/interviews/{session_id}/current-question`
- `POST /v1/interviews/{session_id}/answers`
- `GET /v1/interviews/{session_id}/history`
- `GET /v1/interviews/{session_id}/feedback`
- `GET /v1/interviews/{session_id}/summary`

Both applications expose the same `/v1/interviews` routes. Clients normally use
the Public API on port 8000; it forwards to the Interview Service and preserves
404/409/422/502/503/504 responses without exposing transport details.

Session creation accepts the original BIC-005 body unchanged. Optional BIC-006
configuration fields are `target_role` (2-120 characters), `experience_level`
(`entry`, `mid`, `senior`), `category` (`technical`, `behavioral`, `hr`,
`mixed`), `difficulty` (`beginner`, `intermediate`, `advanced`), and
`question_limit` (1-20). Defaults are Software Engineer, mid, mixed,
intermediate, and `AI_QUESTION_LIMIT`. The stable create/get session response is
unchanged; retrieve the full durable configuration from the configuration route.

## AI provider configuration

The default `AI_PROVIDER=mock` is deterministic, supports English (`en`) and
Sinhala (`si`), requires no key, and is suitable for tests and local demos.
Question limits default from `AI_QUESTION_LIMIT` (1-20, default 5) and can be
overridden safely per session. Provider prompts are centralized and versioned,
include role/category/difficulty and ordered context, request consistent output
language, and allow standard English technical terminology in Sinhala answers.
Provider/model Sinhala quality must still be validated independently.

The real adapter uses the documented OpenAI Responses HTTP API and strict
structured output. Configure it explicitly:

```powershell
$env:AI_PROVIDER = 'openai'
$env:OPENAI_API_KEY = '<local secret>'
$env:OPENAI_MODEL = '<a model available to your OpenAI project>'
$env:AI_TIMEOUT_SECONDS = '20'
$env:AI_MAX_RETRIES = '1'
```

No model identifier is assumed. Never put a real key in `.env.example`, Git,
test fixtures, or CI logs. The adapter retries timeouts, connection failures,
HTTP 429, and 5xx responses with bounded backoff. A timeout maps to 504,
unavailable/configuration failures to 503, and rejected or malformed output to
502. Provider output is validated by typed schemas before any interview cycle
is persisted. See the official [Responses API reference](https://developers.openai.com/api/reference/resources/responses/methods/create)
and [Structured Outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses).

## Text interview API example

Create and start a session (the stable BIC-004 session response is unchanged):

```json
POST /v1/interviews
{"mode":"mock_interview","language":"en"}

201
{"id":"11111111-1111-4111-8111-111111111111","mode":"mock_interview","language":"en","status":"created"}
```

A configured request remains compatible with the same response:

```json
{
  "mode": "mock_interview",
  "language": "si",
  "target_role": "Platform Engineer",
  "experience_level": "senior",
  "category": "technical",
  "difficulty": "advanced",
  "question_limit": 3
}
```

`GET /v1/interviews/{id}/configuration` returns those resolved values, including
`preferred_language` and `question_limit`.

```json
POST /v1/interviews/11111111-1111-4111-8111-111111111111/start

200
{"id":"11111111-1111-4111-8111-111111111111","mode":"mock_interview","language":"en","status":"active"}
```

Retrieve and answer the current question:

```json
GET /v1/interviews/11111111-1111-4111-8111-111111111111/current-question

200
{"id":"22222222-2222-4222-8222-222222222222","sequence":1,"text":"Tell me about your professional background.","topic":"background","provider":"mock","model":"deterministic-interview-v2","created_at":"2026-11-11T08:00:00Z"}
```

```json
POST /v1/interviews/11111111-1111-4111-8111-111111111111/answers
{"question_id":"22222222-2222-4222-8222-222222222222","text":"I led a platform migration that cut deployment time by half."}

200
{
  "answer":{"id":"33333333-3333-4333-8333-333333333333","question_id":"22222222-2222-4222-8222-222222222222","text":"I led a platform migration that cut deployment time by half.","created_at":"2026-11-11T08:01:00Z"},
  "evaluation":{"id":"44444444-4444-4444-8444-444444444444","answer_id":"33333333-3333-4333-8333-333333333333","score":73,"feedback":"The answer is clear; add one more specific example.","strengths":["Directly addresses the question"],"improvements":["Include a measurable outcome"],"criteria":{"relevance":16,"technical_accuracy":14,"clarity":15,"completeness":14,"communication_quality":14},"learning_areas":["Structuring examples with evidence"],"provider":"mock","model":"deterministic-interview-v2","created_at":"2026-11-11T08:01:00Z"},
  "next_question":{"id":"55555555-5555-4555-8555-555555555555","sequence":2,"text":"Following up on your previous answer: Describe a difficult problem you solved.","topic":"problem solving","provider":"mock","model":"deterministic-interview-v2","created_at":"2026-11-11T08:01:00Z"},
  "completed":false
}
```

`history` returns `{interview, items}` with ordered question objects and their
optional answer/evaluation. `feedback` returns `{interview_id, evaluations}`.
After automatic or explicit completion, `summary` returns:

```json
{
  "id":"66666666-6666-4666-8666-666666666666",
  "interview_id":"11111111-1111-4111-8111-111111111111",
  "overall_score":73,
  "summary":"Interview complete. The answers were clear and relevant.",
  "strengths":["Clear communication"],
  "improvements":["Add more specific, measurable outcomes"],
  "provider":"mock",
  "model":"deterministic-interview-v2",
  "created_at":"2026-11-11T08:05:00Z"
}
```

Only the current unanswered question accepts an answer. Duplicate answers,
answers in a non-active session, and an unavailable summary return 409.

The deterministic 100-point rubric assigns 0-20 each for relevance, technical
accuracy, clarity, completeness, and communication quality. For non-technical
questions, accuracy means factual/contextual accuracy. The total must equal the
five scores. Feedback adds learning areas and avoids claims about employability.

## Local mock-provider demonstration

After starting PostgreSQL, applying migrations, and starting both services as
shown above:

```powershell
$created = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/interviews -ContentType application/json -Body '{"mode":"mock_interview","language":"en"}'
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/interviews/$($created.id)/start"
$question = Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/interviews/$($created.id)/current-question"
$body = @{ question_id = $question.id; text = 'I improved release reliability with automated checks.' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/v1/interviews/$($created.id)/answers" -ContentType application/json -Body $body
Invoke-RestMethod -Uri "http://127.0.0.1:8000/v1/interviews/$($created.id)/history"
```

## Database migrations

Apply the latest schema with `uv run alembic upgrade head`. Revision
`20261111_0002` keeps existing session rows, adds the stored question limit,
and creates ordered questions, unique candidate answers, unique evaluations,
and unique final summaries with foreign keys, checks, indexes, provider/model
metadata, and timezone-aware timestamps. Downgrades remove BIC-005 data, so run
them only against disposable databases.

Revision `20261111_0003` preserves existing rows while adding role, experience,
category, difficulty, rubric criteria, and learning areas with safe defaults and
database constraints. Its downgrade removes only the BIC-006 additions.

Revision `20261111_0004` adds one server-owned LiveKit room binding per
interview and idempotent finalized-transcript records. Its downgrade removes
only BIC-007 voice transport data.

## Optional paid-provider smoke validation

The smoke script is never imported by pytest or Jenkins and requires three
separate opt-ins: `AI_PROVIDER=openai`, `LIVE_PROVIDER_SMOKE_ENABLED=1`, and the
literal confirmation argument. It validates typed responses, expected language,
one question/evaluation/summary flow, and reports provider usage metadata when
available without estimating a price or printing credentials.

```powershell
$env:AI_PROVIDER = 'openai'
$env:LIVE_PROVIDER_SMOKE_ENABLED = '1'
$env:OPENAI_API_KEY = '<local secret>'
$env:OPENAI_MODEL = '<model available to your project>'
uv run python scripts/live_provider_smoke.py --language en --confirm-paid-call I_CONFIRM_PAID_API_CALL
uv run python scripts/live_provider_smoke.py --language si --confirm-paid-call I_CONFIRM_PAID_API_CALL
```

Each command makes three provider requests and can incur cost. Run only one at a
time after reviewing the selected model and account limits.

## Test and quality checks

```powershell
uv run ruff check .
uv run ruff format --check .
uv run pytest
uv audit --locked
```

The default suite creates a fresh temporary SQLite database for each test and
uses only mocked/deterministic AI providers. To
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

Jenkins requires no paid API key or provider access and needs no pipeline
change. Its existing locked install, Ruff, pytest/JUnit, and dependency-audit
stages cover this milestone. `AI_PROVIDER` defaults to `mock`; the live smoke
enablement variable remains unset. PostgreSQL integration remains opt-in through
an isolated `TEST_DATABASE_URL` ending in `_test`.

See [BIC-006 architecture and LiveKit readiness](docs/BIC-006-architecture.md)
for service boundaries, the future voice-agent flow, and deferred security and
reconnect requirements.

## LiveKit voice interview prototype

BIC-007 adds LiveKit as a transport over the BIC-006 engine. The worker never
generates questions or scores: it starts or resumes the durable interview,
speaks the persisted current question, submits only finalized STT text to the
existing engine, speaks the returned next question, and retrieves the persisted
summary on completion. Speech configuration is independent of `AI_PROVIDER`.

The installed and locked integration versions are `livekit-agents==1.8.11`,
`livekit-api==1.2.2`, and `livekit-plugins-google==1.8.11`. The local server
image is pinned to `livekit/livekit-server:v1.13.11`; LiveKit Cloud can be used
by setting the same URL/key/secret variables and omitting the local container.

### Local voice setup (PowerShell)

Generate a unique development key pair. Copy the two generated values into the
untracked `.env` file as `LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`; do not use
the documented LiveKit placeholder secret and do not commit `.env`.

```powershell
docker run --rm livekit/livekit-server:v1.13.11 generate-keys
Copy-Item .env.example .env
# Edit .env and set the generated LiveKit values plus the PostgreSQL password.
```

Load the secrets into the current PowerShell process (the Python processes do
not parse `.env` automatically), then start the unchanged PostgreSQL service
and the development-only LiveKit profile:

```powershell
$env:DATABASE_URL = (Get-Content .env | Where-Object { $_ -like 'DATABASE_URL=*' }) -replace '^DATABASE_URL=', ''
$env:LIVEKIT_URL = (Get-Content .env | Where-Object { $_ -like 'LIVEKIT_URL=*' }) -replace '^LIVEKIT_URL=', ''
$env:LIVEKIT_API_KEY = (Get-Content .env | Where-Object { $_ -like 'LIVEKIT_API_KEY=*' }) -replace '^LIVEKIT_API_KEY=', ''
$env:LIVEKIT_API_SECRET = (Get-Content .env | Where-Object { $_ -like 'LIVEKIT_API_SECRET=*' }) -replace '^LIVEKIT_API_SECRET=', ''
$env:LIVEKIT_AGENT_NAME = 'bic-interviewer'
docker compose --profile voice up -d postgres livekit
uv run alembic upgrade head
```

Google Cloud Speech is one real prototype adapter. Enabling it can incur
provider charges, so no command, test, or Jenkins stage enables it
automatically. After enabling Cloud Speech-to-Text and Text-to-Speech in your
own project, set credentials and English defaults in the worker window:

```powershell
$env:VOICE_AUDIO_PROVIDER = 'google'
$env:GOOGLE_APPLICATION_CREDENTIALS = 'C:\path\to\untracked-service-account.json'
$env:GOOGLE_CLOUD_PROJECT = '<your-project-id>'
$env:GOOGLE_STT_LOCATION = 'global'
$env:GOOGLE_STT_MODEL_EN = 'latest_long'
$env:GOOGLE_TTS_MODEL = 'gemini-2.5-flash-tts'
$env:GOOGLE_TTS_VOICE_EN = 'Kore'
$env:VOICE_STT_TIMEOUT_SECONDS = '10'
$env:VOICE_TTS_TIMEOUT_SECONDS = '10'
```

Alternatively, LiveKit Cloud Inference uses the LiveKit Cloud project's key and
secret. It does not call an interview LLM: keep `AI_PROVIDER=mock` (or use the
existing configured BIC AI provider). Models and TTS voices are configurable;
the defaults are `deepgram/nova-3` + `google/gemini-3.8-flash-lite-tts` with
voice `Kore` for English, and `cartesia/ink-whisper` + the same Gemini TTS model
and voice for Sinhala. LiveKit currently lists each model for these languages.
If you override the IDs with unsupported values, worker startup fails clearly.
No model fallback is configured. Do not use LiveKit local-server credentials
for inference; set Cloud credentials in the worker process:

```powershell
$env:VOICE_AUDIO_PROVIDER = 'livekit_inference'
$env:LIVEKIT_INFERENCE_API_KEY = '<your-livekit-cloud-api-key>'
$env:LIVEKIT_INFERENCE_API_SECRET = '<your-livekit-cloud-api-secret>'
$env:LIVEKIT_INFERENCE_STT_MODEL_EN = 'deepgram/nova-3'
$env:LIVEKIT_INFERENCE_STT_MODEL_SI = 'cartesia/ink-whisper'
$env:LIVEKIT_INFERENCE_TTS_MODEL = 'google/gemini-3.8-flash-lite-tts'
$env:LIVEKIT_INFERENCE_TTS_VOICE_EN = 'Kore'
$env:LIVEKIT_INFERENCE_TTS_VOICE_SI = 'Kore'
```

Keep `LIVEKIT_URL`, `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET` configured for
the worker's LiveKit connection as before. Cloud Inference can incur charges;
tests construct mocked adapters and never make inference requests.

Start these three processes in separate PowerShell windows after loading
`DATABASE_URL` and the LiveKit variables into each one:

```powershell
uv run uvicorn interview_service.main:app --host 127.0.0.1 --port 8001
```

```powershell
$env:INTERVIEW_SERVICE_URL = 'http://127.0.0.1:8001'
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Also set the selected provider variables above in this worker window.
uv run python -m interview_service.voice.worker dev
```

Create an interview and open `http://127.0.0.1:8000/voice-demo`:

```powershell
$created = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/v1/interviews -ContentType application/json -Body '{"mode":"mock_interview","language":"en","question_limit":2}'
$created.id
```

Paste that opaque interview UUID into the demo. The demo requests a server-made
token, publishes only the microphone, plays the agent's audio, and polls the
existing API for the current question and completion state.

For LiveKit Cloud, set `LIVEKIT_URL` to the project's `wss://` URL and use its
API key/secret; start only `postgres`, not the Compose `livekit` profile.

### Sinhala capability and limitations

Google Cloud STT documents `si-LK` on specific Chirp models and regions. Google
Gemini-TTS lists Sinhala as Preview. To prevent accidental claims or calls, a
Sinhala worker refuses to start unless `GOOGLE_TTS_VOICE_SI` is explicitly set
to a voice validated in the selected project, model, and region. Configure the
documented supported STT region/model (for example `chirp_2`) and a Gemini-TTS
voice, then test code-switching, accents, latency, and transcription/synthesis
quality yourself. Availability is not a claim of equivalent or production-grade
Sinhala quality. Deepgram Nova-3's current LiveKit language list does not list
Sinhala, so it is not exposed as a Sinhala option here.

See [BIC-007 architecture](docs/BIC-007-architecture.md) for lifecycle,
security, persistence, reconnect behavior, and remaining production gaps.

## Limitations and deferred scope

- **AUTH-001:** Add OAuth2/OIDC authentication and JWT validation.
- The REST experience remains text-first; the included voice page is a local
  verification client, not the BIC-008 production frontend.
- Prompt quality and production model selection need evaluation against real
  interview rubrics before a real provider is enabled.
- Provider calls are synchronous and bounded; background processing, streaming,
  rate limiting, and per-user quotas are future work.
- No authentication or tenant isolation exists yet; do not expose this service
  directly to untrusted networks.

