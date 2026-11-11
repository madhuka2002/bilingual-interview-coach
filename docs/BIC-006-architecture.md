# BIC-006 architecture and LiveKit readiness

## Implementation plan

1. Extend the durable session configuration without changing the existing
   session response contract.
2. Pass one provider-neutral configuration object and ordered history through
   every orchestration operation.
3. enforce and persist an explicit 100-point rubric, then cover configuration,
   bilingual prompts, follow-ups, forwarding, and migration reversal in tests.
4. Keep real-provider validation standalone, paid-call opt-in, and outside CI.

## Boundaries

The Public API remains an HTTP forwarding boundary. The Interview Service owns
validation and persistence. `engine.py` owns transport-independent operations:
start/get current question, submit answer/get feedback, complete, and retrieve
history. Provider adapters only generate typed results. Consequently, neither
REST nor a future voice transport owns interview state.

The persisted configuration is target role, experience level, category,
difficulty, preferred language, and question limit. A voice agent can retrieve
it with `GET /v1/interviews/{id}/configuration` and use the same start,
current-question, answer, feedback, history, and summary operations as REST.

## Prompting and evaluation

Prompts are centralized in `interview_service/ai/prompts.py` and carry the
`bic-006-v1` version marker. Sinhala instructions explicitly allow established
English technical terminology rather than forcing awkward translations.
Providers receive the complete ordered history for contextual follow-ups. The
provider contract does not claim equal language quality across providers; each
adapter/model must be validated independently.

Each answer receives five equally weighted 0–20 scores: relevance, technical
accuracy (factual/contextual accuracy for non-technical questions), clarity,
completeness, and communication quality. The overall 0–100 score must equal the
sum. Feedback contains strengths, improvements, and learning areas. Prompts
prohibit unsupported employability or broad competence claims.

## LiveKit handoff

BIC-007 implements the following flow as an additive transport. See
`docs/BIC-007-architecture.md` for the realized persistence, security, worker,
provider, reconnect, and demo design.

1. An authenticated application creates or resumes an Interview Service
   session and issues a short-lived room/session token.
2. A LiveKit Agent maps a room participant to the durable interview ID.
3. The agent gets the current question or starts the interview, speaks the
   returned text, and submits only finalized transcripts as answers.
4. The agent reads the persisted evaluation and next question. Reconnects use
   current-question/history rather than in-memory agent state.
5. Completion retrieves the same persisted summary used by text clients.

Before integration, define OAuth2/OIDC service authentication, authorization
between user/room/interview IDs, short-lived scoped LiveKit tokens, webhook
verification, transcript provenance and confidence, idempotency keys for final
transcripts, interruption/barge-in semantics, partial-transcript handling,
reconnect ownership, room cleanup, consent and retention, rate limits, and
observability. Audio, STT, TTS, LiveKit dependencies, and frontend work remain
deliberately out of scope.

## Risks

- Sinhala fluency and code-switching vary by provider and model; the mock only
  verifies contracts and deterministic flow.
- A synchronous provider call holds the request open; future voice latency may
  require durable asynchronous orchestration.
- There is no authentication or tenant isolation yet.
- Provider token usage is captured by the optional smoke script when returned,
  but prices are intentionally not estimated.
