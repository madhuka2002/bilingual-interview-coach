# BIC-008C voice reliability

The worker uses an event-loop-local conversation controller to gate finalized
transcripts. It accepts answers only during candidate or clarification turns;
playback, answer processing, completion, and failure reject incoming final STT
events. Terminal states cannot transition back into an active interview. The
existing database transaction and uniqueness constraints remain authoritative
for persisted answer and skip idempotency.

The candidate turn buffer joins finalized STT segments and removes repeated
event IDs during one worker process. It is intentionally in memory. An
interrupted worker loses any segments that have not reached the quiet-window
submission point; those words are not silently submitted on restart. The
candidate resumes the durable current question and can answer it again. Durable
buffering of incomplete speech is not implemented.

Automated coverage uses the mock interview provider, fake TTS, in-memory buffers,
and test databases. No paid AI provider or LiveKit Cloud request is required.
This coverage does not emulate a real LiveKit job restart, microphone timing,
network reconnection, or provider-side interruption behavior. A controlled local
LiveKit voice test is still needed to assess those transport behaviors.
