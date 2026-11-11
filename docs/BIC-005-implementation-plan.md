# BIC-005 Implementation Plan

## Current contracts to preserve

- The two existing FastAPI applications remain independently runnable.
- Session creation accepts `mock_interview|career_coach` and `en|si`.
- Existing session responses remain `{id, mode, language, status}`.
- The lifecycle remains `created -> active -> completed`; repeated start/complete
  requests remain idempotent and invalid transitions remain HTTP 409.
- The Public API continues to sanitize service-boundary errors and preserve the
  established 404, 409, 502, 503, and 504 behavior.
- Tests remain independent of paid AI calls and development data.

## Architecture

1. Add an AI provider package with a provider protocol and typed question,
   evaluation, and summary results. Implement a deterministic mock provider and
   a real HTTP adapter configured entirely through environment variables.
   Provider output is validated before business logic can persist it.
2. Add an interview engine service that owns state rules and transaction
   boundaries. Starting generates the first question. Submitting an answer
   evaluates it and either generates the next question or completes the
   session with a summary at the configured limit. Explicit completion remains
   supported for BIC-004 compatibility and produces a summary.
3. Extend persistence with ordered questions, one answer per question, one
   evaluation per answer, and one summary per session. Use foreign keys, unique
   constraints, checks, and timezone-aware timestamps. Provider calls happen
   before a flush of the corresponding cycle so failures cannot leave a
   partial answer/evaluation/question cycle.
4. Add Interview Service read endpoints for the current question, complete
   history, evaluation feedback, and final summary, plus an answer submission
   endpoint. Add matching transparent Public API routes.
5. Expand automated coverage for successful flows, invalid states,
   idempotency/duplicates, provider timeouts and malformed output, rollback,
   persistence, forwarding, migrations, and all BIC-004 regressions.

## State and failure rules

- A created session has no question. Starting it generates sequence 1 and
  transitions it to active in one committed request.
- Only the current unanswered question accepts an answer. An answer is
  non-empty, has a bounded size, and identifies its question. A second answer
  for that question returns 409.
- Active sessions expose one current unanswered question. Completed sessions
  cannot accept answers or generate questions.
- The question limit is stored on each session so later environment changes do
  not alter an interview already in progress.
- Provider timeout returns 504, unavailable/misconfigured provider returns 503,
  and upstream or malformed provider output returns 502. No provider exception
  details or credentials are returned to clients.
- A failed first-question call leaves the session created. A failed answer
  cycle leaves the previous committed history unchanged and the question still
  answerable.

## Verification

- Run locked pytest, Ruff lint, Ruff formatting check, dependency audit, and
  `git diff --check`.
- Run Alembic upgrade/downgrade smoke coverage and, when an isolated `_test`
  PostgreSQL database is available, run the suite against it without touching
  development data.
- No UI work is in scope, so desktop/mobile layout verification is not
  applicable.
