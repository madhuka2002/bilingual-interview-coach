# BIC-007 LiveKit voice architecture

## Boundaries

LiveKit is an additive voice transport. `interview_service.engine` remains the
only owner of interview start/resume, questions, answer submission, evaluation,
next-question generation, completion, and summaries. The worker has no LLM and
cannot generate interview content. The separate speech adapter only converts
audio to finalized text and persisted text to audio.

The browser continues to use the Public API. `POST
/v1/interviews/{id}/voice/token` is additive and forwards to the Interview
Service, where the room binding and token are created. All BIC-006 response
contracts remain unchanged.

## Durable voice state

Migration `20261111_0004` adds:

- `voice_rooms`: one opaque room name and opaque candidate identity per
  interview, both server generated and unique.
- `voice_transcripts`: finalized STT text, its source event key, participant,
  question, and processing timestamps. Unique room/event and question
  constraints prevent repeat persistence, including concurrent delivery races.

Partial transcripts never enter either the answer or transcript tables. If the
worker or participant reconnects, the worker reads the session, current
unanswered question, history, and summary from PostgreSQL. It does not depend on
in-memory conversation state.

## Lifecycle

1. The application creates a normal interview through BIC-006.
2. The candidate requests the fixed voice-token route. The server creates or
   reuses the interview's room binding and signs a short-lived participant JWT.
3. The token's room configuration dispatches the named BIC worker with only the
   opaque interview ID and room name in metadata.
4. The worker validates metadata, room, candidate identity, and durable binding.
5. A created interview is started through the existing engine. An active
   interview resumes its current unanswered question. A completed interview
   retrieves its persisted summary.
6. The worker speaks question text using TTS with interruptions disabled during
   playout. The session then listens with STT endpointing and bounded timeouts.
7. Interim events are ignored. A final event is idempotently recorded and sent
   to `engine.submit_answer`; the resulting next question or final summary is
   then spoken.
8. Completion or provider failure shuts the job down gracefully. A subsequent
   connection reconstructs state from PostgreSQL.

## Security design

- API keys and secrets are environment-only. The browser receives a signed JWT,
  never the signing secret.
- The endpoint accepts no caller-selected room or participant identity.
- Room and identity values are opaque UUID-derived identifiers, not PII.
- Candidate JWTs expire after 10 minutes by default (maximum one hour), join one
  room, publish only a microphone source, subscribe to agent audio, cannot
  publish data, cannot update metadata, and have no room-admin or agent grant.
- Rooms allow two participants and have short empty/departure timeouts.
- Worker dispatch metadata and the joining participant are checked against the
  stored interview/room association before interview work begins.
- Transcript uniqueness and the existing one-answer-per-question constraint
  provide defense in depth against duplicate final events.
- Logs use interview UUIDs and sanitized failure messages; provider credentials
  and transcript contents are not logged by application code.

The repository still has no end-user authentication or tenant ownership check
(`AUTH-001`). Knowledge of an interview UUID is therefore sufficient to request
its candidate token. Keep this prototype on localhost or behind a trusted
authenticated application boundary; this is not production authorization.

## Speech providers

`VOICE_AUDIO_PROVIDER` is intentionally independent from `AI_PROVIDER`:

- `fake`: deterministic, network-free STT/TTS test adapters; a real worker
  refuses to start with it.
- `google`: LiveKit's Google plugin for Cloud STT and Cloud TTS. English defaults
  are configurable. Sinhala requires explicit TTS voice selection and provider
  validation before worker startup.
- `livekit_inference`: LiveKit's `inference.STT` and `inference.TTS`, authenticated
  with explicit LiveKit Cloud Inference credentials. Defaults are
  `deepgram/nova-3` for English STT, `cartesia/ink-whisper` for Sinhala STT,
  and `google/gemini-3.8-flash-lite-tts` with the configured `Kore` voice for
  either language. The provider validates supported configured IDs and
  language before constructing SDK adapters and configures no model fallback.

The LiveKit Python SDK also exposes plugins or managed models for providers such
as AssemblyAI, Azure Speech, Cartesia, Deepgram, ElevenLabs, Gemini, and others;
their exact model/language matrices change independently. BIC-007 deliberately
does not claim them as configured providers beyond the explicit LiveKit
Inference selection above. Interview LLM support remains the existing BIC `mock` or
`openai` adapter. The LiveKit session sets `llm=None`.

STT finalization and TTS playout have explicit timeouts. Provider/session error
events close the job without persisting partial input. Inference adapter tests
mock the SDK constructors and make no paid calls.

Official provider availability changes independently of this repository.
Google documents Sinhala STT only for particular models/regions, and its
Gemini-TTS Sinhala entry is Preview. That indicates capability, not expected
accuracy, naturalness, code-switching quality, or latency. Those need recorded
evaluation with representative Sri Lankan speakers before production use.

## Local and Cloud infrastructure

The existing PostgreSQL service is unchanged. Compose adds a `voice` profile
containing pinned LiveKit Server `v1.13.11`. `LIVEKIT_KEYS` is assembled from
untracked environment values; no key or secret is stored in the repository.
The same application variables accept a LiveKit Cloud `wss://` URL and Cloud
credentials without running the local service.

Jenkins is unchanged. Its locked install now includes the LiveKit packages, and
the existing Ruff, pytest/JUnit, and dependency-audit stages cover the new code.
The test default remains `VOICE_AUDIO_PROVIDER=fake`, so CI needs no LiveKit
server, Google credentials, microphone, or paid provider access.

## Remaining limitations

- The voice-token route currently has no candidate ownership authentication.
  Anyone with an interview UUID can request the room-bound candidate token.
  Keep the demo and token endpoint local-only until AUTH-001 is implemented.
- `AUTH-001`: authenticated users, interview ownership, tenant isolation, token
  refresh/revocation, and rate limiting remain required for production.
- The demo loads the pinned LiveKit browser SDK from jsDelivr and is intended for
  local verification, not offline or production delivery.
- No webhook verification, consent UI, transcript-retention policy,
  observability dashboard, or distributed worker ownership/lease is included.
- Google speech calls are synchronous with the live session and need real-world
  latency, outage, quota, and fallback testing.
- Sinhala STT/TTS is capability-gated but not quality-certified.
- BIC-008 owns the production React experience.
