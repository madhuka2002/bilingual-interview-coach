"""Transport-neutral voice interview lifecycle tests."""

from uuid import uuid4

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from interview_service.ai.mock import MockAIProvider
from interview_service.models import (
    CandidateAnswer,
    InterviewSession,
    VoiceRoom,
    VoiceTranscript,
)
from interview_service.voice.audio import FakeTTSAdapter
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


def test_candidate_turn_buffer_combines_segments_and_deduplicates() -> None:
    buffer = CandidateTurnBuffer()
    assert buffer.add("I reduced latency", "segment-1")
    assert not buffer.add("I reduced latency", "segment-1")
    assert buffer.add("by 30 percent", "segment-2")
    assert buffer.take() == "I reduced latency by 30 percent"
    assert buffer.take() == ""


@pytest.mark.parametrize(
    ("utterance", "intent"),
    [
        ("Could you repeat the question?", CandidateIntent.REPEAT),
        ("Can you explain the question?", CandidateIntent.EXPLAIN),
        ("Give me a moment, please", CandidateIntent.MOMENT),
        ("I don't understand", CandidateIntent.UNCLEAR),
        ("Skip this question", CandidateIntent.SKIP),
        ("I used caching to reduce response time", CandidateIntent.ANSWER),
    ],
)
def test_candidate_intent_classification(utterance, intent) -> None:
    assert classify_candidate_intent(utterance) == intent


def voice_interview(
    session: Session, *, question_limit: int = 2
) -> tuple[InterviewSession, VoiceRoom]:
    interview = InterviewSession(
        mode="mock_interview",
        language="en",
        max_questions=question_limit,
    )
    session.add(interview)
    session.flush()
    room = VoiceRoom(
        interview_id=interview.id,
        room_name=f"bic-{uuid4().hex}",
        candidate_identity=f"candidate-{uuid4().hex}",
    )
    session.add(room)
    session.commit()
    return interview, room


@pytest.mark.anyio
async def test_startup_speaks_first_question_and_reconnect_resumes(
    database_engine: Engine,
) -> None:
    provider = MockAIProvider()
    speaker = FakeTTSAdapter()
    with Session(database_engine) as session:
        interview, room = voice_interview(session)
        first = start_or_resume_voice_session(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            provider,
        )
        session.commit()
        await speak_turn(speaker, first)
        resumed = start_or_resume_voice_session(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            provider,
        )

    assert first.question_id is not None
    assert speaker.spoken == [first.question_text]
    assert resumed.question_id == first.question_id
    assert resumed.question_text == first.question_text


@pytest.mark.anyio
async def test_partial_is_not_persisted_then_final_advances_and_deduplicates(
    database_engine: Engine,
) -> None:
    provider = MockAIProvider()
    speaker = FakeTTSAdapter()
    with Session(database_engine) as session:
        interview, room = voice_interview(session)
        first = start_or_resume_voice_session(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            provider,
        )
        session.commit()
        partial = process_final_transcript(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            "unfinished",
            provider,
            event_id="event-1",
            is_final=False,
        )
        assert session.scalar(select(func.count(VoiceTranscript.id))) == 0
        assert session.scalar(select(func.count(CandidateAnswer.id))) == 0

        final = process_final_transcript(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            "A complete answer with a measurable result.",
            provider,
            event_id="event-1",
            is_final=True,
        )
        session.commit()
        await speak_turn(speaker, final)
        duplicate = process_final_transcript(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            "A complete answer with a measurable result.",
            provider,
            event_id="event-1",
            is_final=True,
        )

        transcript_count = session.scalar(select(func.count(VoiceTranscript.id)))
        answer_count = session.scalar(select(func.count(CandidateAnswer.id)))

    assert partial.disposition == TranscriptDisposition.PARTIAL_IGNORED
    assert final.disposition == TranscriptDisposition.PROCESSED
    assert final.question_id != first.question_id
    assert speaker.spoken == [final.question_text]
    assert duplicate.disposition == TranscriptDisposition.DUPLICATE_IGNORED
    assert transcript_count == 1
    assert answer_count == 1


@pytest.mark.anyio
async def test_final_answer_completes_and_speaks_persisted_summary(
    database_engine: Engine,
) -> None:
    provider = MockAIProvider()
    speaker = FakeTTSAdapter()
    with Session(database_engine) as session:
        interview, room = voice_interview(session, question_limit=1)
        start_or_resume_voice_session(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            provider,
        )
        session.commit()
        completed = process_final_transcript(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            "I improved reliability by adding automated deployment checks.",
            provider,
            event_id=None,
            is_final=True,
        )
        session.commit()
        await speak_turn(speaker, completed)
        resumed = start_or_resume_voice_session(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            provider,
        )

    assert completed.completed is True
    assert completed.summary_text
    assert speaker.spoken[0].startswith("Interview complete.")
    assert completed.summary_text in speaker.spoken[0]
    assert resumed.completed is True
    assert resumed.summary_text == completed.summary_text


def test_skip_is_persisted_without_candidate_answer_and_duplicate_is_safe(
    database_engine: Engine,
) -> None:
    provider = MockAIProvider()
    with Session(database_engine) as session:
        interview, room = voice_interview(session, question_limit=3)
        start_or_resume_voice_session(
            session, interview.id, room.room_name, room.candidate_identity, provider
        )
        session.commit()
        skipped = process_final_transcript(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            "Skip this question",
            provider,
            event_id="skip-1",
            is_final=True,
        )
        session.commit()
        question_count = len(session.get(InterviewSession, interview.id).questions)
        answers = session.scalar(select(func.count(CandidateAnswer.id)))
        duplicate = process_final_transcript(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            "Skip this question",
            provider,
            event_id="skip-1",
            is_final=True,
        )
    assert skipped.question_id is not None
    assert skipped.disposition == TranscriptDisposition.SKIPPED
    assert question_count == 2
    assert answers == 0
    assert duplicate.disposition == TranscriptDisposition.DUPLICATE_IGNORED


@pytest.mark.anyio
async def test_three_question_interview_supports_multisegment_answer_and_skip(
    database_engine: Engine,
) -> None:
    provider = MockAIProvider()
    buffer = CandidateTurnBuffer()
    assert buffer.add("I improved throughput", "segment-a")
    assert buffer.add("by 30 percent.", "segment-b")
    with Session(database_engine) as session:
        interview, room = voice_interview(session, question_limit=3)
        current = start_or_resume_voice_session(
            session, interview.id, room.room_name, room.candidate_identity, provider
        )
        session.commit()
        first = process_final_transcript(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            buffer.take(),
            provider,
            event_id="answer-1",
            is_final=True,
        )
        session.commit()
        skipped = process_final_transcript(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            "Skip this question",
            provider,
            event_id="skip-2",
            is_final=True,
        )
        session.commit()
        last = process_final_transcript(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            "I tested the change and reduced failures by half.",
            provider,
            event_id="answer-3",
            is_final=True,
        )
        session.commit()
        completed = start_or_resume_voice_session(
            session, interview.id, room.room_name, room.candidate_identity, provider
        )

        answer_count = session.scalar(select(func.count(CandidateAnswer.id)))
        transcript_count = session.scalar(select(func.count(VoiceTranscript.id)))

    assert current.question_id is not None
    assert first.disposition == TranscriptDisposition.PROCESSED
    assert skipped.disposition == TranscriptDisposition.SKIPPED
    assert last.completed
    assert completed.completed
    assert answer_count == 2
    assert transcript_count == 3


def test_repeat_and_clarification_are_not_persisted_as_answers(
    database_engine: Engine,
) -> None:
    provider = MockAIProvider()
    with Session(database_engine) as session:
        interview, room = voice_interview(session)
        initial = start_or_resume_voice_session(
            session, interview.id, room.room_name, room.candidate_identity, provider
        )
        session.commit()
        for event_id, utterance in (
            ("repeat", "Could you repeat the question?"),
            ("clarify", "Can you explain the question?"),
        ):
            turn = process_final_transcript(
                session,
                interview.id,
                room.room_name,
                room.candidate_identity,
                utterance,
                provider,
                event_id=event_id,
                is_final=True,
            )
            assert turn.disposition == TranscriptDisposition.CLARIFICATION
            assert turn.question_id == initial.question_id
        assert session.scalar(select(func.count(CandidateAnswer.id))) == 0
        assert session.scalar(select(func.count(VoiceTranscript.id))) == 0


@pytest.mark.anyio
async def test_invalid_identity_blank_final_and_tts_failure_are_safe(
    database_engine: Engine,
) -> None:
    provider = MockAIProvider()
    with Session(database_engine) as session:
        interview, room = voice_interview(session)
        turn = start_or_resume_voice_session(
            session,
            interview.id,
            room.room_name,
            room.candidate_identity,
            provider,
        )
        session.commit()
        with pytest.raises(VoiceSessionError, match="not authorized"):
            process_final_transcript(
                session,
                interview.id,
                room.room_name,
                "candidate-attacker",
                "answer",
                provider,
                event_id="event",
                is_final=True,
            )
        with pytest.raises(VoiceSessionError, match="must not be blank"):
            process_final_transcript(
                session,
                interview.id,
                room.room_name,
                room.candidate_identity,
                "   ",
                provider,
                event_id="event",
                is_final=True,
            )
        with pytest.raises(RuntimeError, match="fake TTS failure"):
            await speak_turn(FakeTTSAdapter(fail=True), turn)
        assert session.scalar(select(func.count(CandidateAnswer.id))) == 0
