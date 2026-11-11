# BIC-007 implementation plan

## Audited boundary

BIC-006 already owns the durable interview lifecycle, configuration, question
generation, evaluation, and summaries. BIC-007 will add voice as a transport;
it will not add another interview engine or a conversational model that can
generate interview content.

## Plan

1. Add a one-to-one durable association between an interview and an opaque
   LiveKit room, plus finalized-transcript records with idempotency keys and
   processing state. Preserve all existing interview API response contracts.
2. Add a server-side token endpoint behind the existing public API. Generate
   and validate room names and candidate identities on the server, issue
   short-lived room-scoped grants, permit candidate microphone publication and
   agent-audio subscription only, and never return or log the API secret.
3. Implement a transport-neutral voice-session orchestrator over the BIC-006
   engine. It will start or resume a session, obtain the current persisted
   question, process finalized transcripts exactly once, submit answers through
   the existing engine, announce the next question, and return the persisted
   final summary.
4. Implement a LiveKit Agents worker as a thin adapter around the orchestrator.
   It will validate the room/interview binding, recover state after reconnects,
   speak persisted question text, ignore partial transcripts, handle safe
   interruption, and close gracefully on disconnect or speech-provider errors.
   It will not configure a separate conversational LLM.
5. Add an environment-driven audio-provider factory separate from the existing
   interview AI provider. Provide deterministic fake STT/TTS adapters for tests
   and a Google Cloud speech plugin path for local English or Sinhala trials,
   with explicit configuration validation and timeouts. Capability checks will
   reject unsupported language/provider combinations before worker startup.
6. Extend the development Compose file with LiveKit only; keep PostgreSQL and
   Jenkins definitions unchanged. Support the same application configuration
   against LiveKit Cloud or a local server.
7. Add a minimal static browser demonstration for microphone publication,
   agent audio, connection state, current-question display, and completion.
   Verify it at desktop and mobile widths.
8. Add automated tests for token scope and binding, startup/resume, first and
   next question speech, finalized transcript submission, duplicate protection,
   reconnect recovery, completion, partial-transcript rejection, and STT/TTS
   failures. All CI tests will use fakes and make no paid provider calls.
9. Update README, `.env.example`, and architecture documentation. Lock and
   inspect the installed LiveKit versions and run pytest, Ruff lint/format,
   dependency audit, and `git diff --check`.

## Provider findings

- LiveKit Agents supports separate STT and TTS plugins and an `AgentSession`
  event model suitable for finalized-transcript handling.
- Google Cloud Speech-to-Text lists `si-LK` for specific Chirp models/regions.
  Google TTS support varies by model; Sinhala availability includes preview
  offerings. Availability is not evidence of production quality.
- Deepgram's current LiveKit Nova-3 language list does not include Sinhala, so
  it is not a Sinhala-capable choice for this prototype.
- No paid or network speech call will run automatically in tests or Jenkins.

## Security limits

The repository still lacks end-user OAuth2/OIDC authentication (AUTH-001).
This prototype will enforce interview/room binding, opaque identities, narrow
room grants, and short token lifetimes, but it must remain local or behind a
trusted application boundary until user authentication and tenant ownership
checks are added.
