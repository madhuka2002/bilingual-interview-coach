"""LiveKit Agents worker for BIC voice interviews."""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from uuid import UUID

from livekit import agents
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    TurnHandlingOptions,
    UserInputTranscribedEvent,
)
from sqlalchemy.orm import Session

from interview_service.ai.config import get_ai_provider
from interview_service.database import get_engine
from interview_service.models import InterviewSession, VoiceRoom
from interview_service.voice.audio import build_livekit_audio
from interview_service.voice.config import (
    AudioProviderSettings,
    LiveKitSettings,
    VoiceConfigurationError,
)
from interview_service.voice.orchestrator import (
    CandidateIntent,
    CandidateTurnBuffer,
    TranscriptDisposition,
    VoiceSessionError,
    classify_candidate_intent,
    process_final_transcript,
    speak_turn,
    start_or_resume_voice_session,
)
from interview_service.voice.state import ConversationState, ConversationStateController

logger = logging.getLogger(__name__)


@dataclass
class LiveKitSpeaker:
    session: AgentSession
    timeout_seconds: float

    async def speak(self, text: str) -> None:
        async with asyncio.timeout(self.timeout_seconds):
            handle = self.session.say(text, allow_interruptions=False)
            await handle.wait_for_playout()


def _persist_turn(interview_id, room_name, candidate_identity, text, event_id):
    """Run the whole synchronous SQLAlchemy transaction outside the event loop."""
    with Session(get_engine()) as database_session:
        turn = process_final_transcript(
            database_session,
            interview_id,
            room_name,
            candidate_identity,
            text,
            get_ai_provider(),
            event_id=event_id,
            is_final=True,
        )
        database_session.commit()
        return turn


def _job_binding(ctx: agents.JobContext) -> tuple[UUID, str]:
    try:
        metadata = json.loads(ctx.job.metadata)
        interview_id = UUID(metadata["interview_id"])
        room_name = metadata["room_name"]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise VoiceSessionError("Invalid voice job metadata") from error
    if room_name != ctx.room.name:
        raise VoiceSessionError("Voice job room does not match its interview binding")
    return interview_id, room_name


def create_agent_server(
    livekit_settings: LiveKitSettings,
    audio_settings: AudioProviderSettings,
) -> AgentServer:
    """Create a worker after all environment configuration has been validated."""
    if audio_settings.provider == "fake":
        raise VoiceConfigurationError(
            "VOICE_AUDIO_PROVIDER=fake is test-only; choose a real worker provider"
        )
    server = AgentServer()

    @server.rtc_session(agent_name=livekit_settings.agent_name)
    async def interview_agent(ctx: agents.JobContext) -> None:
        interview_id, room_name = _job_binding(ctx)

        def load_binding() -> tuple[str, str]:
            with Session(get_engine()) as database_session:
                interview = database_session.get(InterviewSession, interview_id)
                room = (
                    database_session.query(VoiceRoom)
                    .filter_by(interview_id=interview_id, room_name=room_name)
                    .one_or_none()
                )
                if interview is None or room is None:
                    raise VoiceSessionError("Voice room binding was not found")
                return interview.language, room.candidate_identity

        language, candidate_identity = await asyncio.to_thread(load_binding)

        audio_settings.validate_language(language)
        stt, tts = build_livekit_audio(audio_settings, language)
        await ctx.connect()
        participant = await ctx.wait_for_participant(identity=candidate_identity)
        if participant.identity != candidate_identity:
            raise VoiceSessionError("Unexpected participant identity")

        agent_session = AgentSession(
            stt=stt,
            tts=tts,
            llm=None,
            transcription_timeout=audio_settings.stt_timeout_seconds,
            turn_handling=TurnHandlingOptions(
                turn_detection="stt",
                endpointing={"min_delay": 0.6, "max_delay": 3.0},
                interruption={
                    "enabled": True,
                    "mode": "vad",
                    "min_duration": 0.5,
                    "min_words": 1,
                    # Preserve buffered candidate speech for STT during interviewer
                    # playback; the controller gates its submission until playout ends.
                    "discard_audio_if_uninterruptible": False,
                },
            ),
        )
        await agent_session.start(
            room=ctx.room,
            agent=Agent(
                instructions=(
                    "Deliver only persisted BIC interview questions. "
                    "Do not generate questions, answers, feedback, or scores."
                ),
                llm=None,
            ),
        )
        speaker = LiveKitSpeaker(agent_session, audio_settings.tts_timeout_seconds)
        processing_lock = asyncio.Lock()
        turn_buffer = CandidateTurnBuffer()
        end_turn_seconds = float(os.getenv("VOICE_END_OF_TURN_SECONDS", "1.8"))
        if not 0.5 <= end_turn_seconds <= 8:
            raise VoiceConfigurationError("VOICE_END_OF_TURN_SECONDS must be 0.5–8")
        accepting_candidate = False
        finalize_task: asyncio.Task | None = None
        playout_complete = asyncio.Event()
        playout_complete.set()
        state = ConversationState.INTERVIEWER_SPEAKING
        controller = ConversationStateController(state)

        def schedule_finalize() -> None:
            nonlocal finalize_task
            if finalize_task and not finalize_task.done():
                finalize_task.cancel()
            finalize_task = asyncio.create_task(finalize_buffer())

        async def deliver(turn, submitted_text: str = "") -> None:
            nonlocal accepting_candidate, state
            accepting_candidate = False
            if turn.disposition == TranscriptDisposition.CLARIFICATION:
                intent = classify_candidate_intent(submitted_text)
                message = (
                    turn.question_text or ""
                    if intent == CandidateIntent.REPEAT
                    else (
                        "I can clarify. Which part of the question would you like "
                        "me to explain?"
                    )
                )
                playout_complete.clear()
                await speaker.speak(message)
                playout_complete.set()
                accepting_candidate = True
                controller.transition(ConversationState.CLARIFICATION)
                state = ConversationState.CLARIFICATION
                if turn_buffer.segments:
                    schedule_finalize()
                return
            if turn.disposition == TranscriptDisposition.SKIP_REQUEST:
                playout_complete.clear()
                await speaker.speak(
                    "I can skip it. Please say 'skip this question' again to "
                    "confirm, or answer when you are ready."
                )
                playout_complete.set()
                accepting_candidate = True
                controller.transition(ConversationState.CLARIFICATION)
                state = ConversationState.CLARIFICATION
                if turn_buffer.segments:
                    schedule_finalize()
                return
            if turn.disposition == TranscriptDisposition.SKIPPED:
                state = ConversationState.INTERVIEWER_SPEAKING
                playout_complete.clear()
                await speak_turn(speaker, turn)
                playout_complete.set()
                accepting_candidate = not turn.completed
                state = (
                    ConversationState.COMPLETED
                    if turn.completed
                    else ConversationState.CANDIDATE_SPEAKING
                )
                controller.transition(state)
                if turn.completed:
                    ctx.shutdown("interview completed")
                elif turn_buffer.segments:
                    schedule_finalize()
                return
            if turn.disposition == TranscriptDisposition.PROCESSED:
                playout_complete.clear()
                await speak_turn(speaker, turn)
                playout_complete.set()
            accepting_candidate = not turn.completed
            state = (
                ConversationState.COMPLETED
                if turn.completed
                else ConversationState.CANDIDATE_SPEAKING
            )
            controller.transition(state)
            if turn.completed:
                ctx.shutdown("interview completed")
            elif turn_buffer.segments:
                schedule_finalize()

        async def finalize_buffer() -> None:
            nonlocal accepting_candidate, state
            await asyncio.sleep(end_turn_seconds)
            await playout_complete.wait()
            async with processing_lock:
                text = turn_buffer.take()
                if (
                    not text
                    or not accepting_candidate
                    or not controller.can_accept_answer()
                ):
                    return
                try:
                    controller.transition(ConversationState.ANSWER_PROCESSING)
                    state = ConversationState.ANSWER_PROCESSING
                    turn = await asyncio.to_thread(
                        _persist_turn,
                        interview_id,
                        room_name,
                        candidate_identity,
                        text,
                        None,
                    )
                    await deliver(turn, text)
                except Exception:
                    controller.transition(ConversationState.FAILED)
                    state = ConversationState.FAILED
                    logger.exception("Voice turn failed for interview %s", interview_id)
                    ctx.shutdown("voice turn failed")

        async def process_event(event: UserInputTranscribedEvent) -> None:
            nonlocal finalize_task
            if not event.is_final:
                return
            if not controller.can_accept_answer():
                return
            # Finals describe transcript items, not completed answers. Buffer while
            # TTS plays and let the end-of-turn window decide when to submit.
            if not turn_buffer.add(event.transcript, event.item_id):
                return
            if playout_complete.is_set():
                nonlocal state
                state = ConversationState.CANDIDATE_SPEAKING
            if accepting_candidate and playout_complete.is_set():
                schedule_finalize()

        @agent_session.on("user_input_transcribed")
        def on_transcript(event: UserInputTranscribedEvent) -> None:
            asyncio.create_task(process_event(event))

        @agent_session.on("error")
        def on_speech_provider_error(_event: object) -> None:
            logger.error(
                "LiveKit speech provider failed for interview %s", interview_id
            )
            ctx.shutdown("speech provider failure")

        try:

            def start_turn():
                with Session(get_engine()) as database_session:
                    turn = start_or_resume_voice_session(
                        database_session,
                        interview_id,
                        room_name,
                        candidate_identity,
                        get_ai_provider(),
                    )
                    database_session.commit()
                    return turn

            turn = await asyncio.to_thread(start_turn)
            playout_complete.clear()
            await speak_turn(speaker, turn)
            playout_complete.set()
            accepting_candidate = not turn.completed
            state = (
                ConversationState.COMPLETED
                if turn.completed
                else ConversationState.CANDIDATE_SPEAKING
            )
            controller.transition(state)
            if not turn.completed and turn_buffer.segments:
                schedule_finalize()
            if turn.completed:
                ctx.shutdown("interview already completed")
        except Exception:
            logger.exception("Unable to start voice interview %s", interview_id)
            ctx.shutdown("voice session startup failed")

    return server


def main() -> None:
    livekit_settings = LiveKitSettings.from_env()
    audio_settings = AudioProviderSettings.from_env()
    server = create_agent_server(livekit_settings, audio_settings)
    agents.cli.run_app(server)


if __name__ == "__main__":
    main()
