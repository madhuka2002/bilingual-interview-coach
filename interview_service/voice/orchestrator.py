"""Voice lifecycle orchestration over the existing interview engine."""

import hashlib
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from interview_service.ai.base import AIProvider
from interview_service.engine import (
    current_question,
    get_history,
    skip_question,
    start_interview,
    submit_answer,
)
from interview_service.models import (
    InterviewSession,
    InterviewStatus,
    VoiceRoom,
    VoiceTranscript,
    utc_now,
)


class VoiceSessionError(RuntimeError):
    """A public-safe voice session validation or lifecycle failure."""


class TranscriptDisposition(StrEnum):
    PARTIAL_IGNORED = "partial_ignored"
    DUPLICATE_IGNORED = "duplicate_ignored"
    PROCESSED = "processed"
    CLARIFICATION = "clarification"
    SKIP_REQUEST = "skip_request"
    SKIPPED = "skipped"


class CandidateIntent(StrEnum):
    ANSWER = "answer"
    REPEAT = "repeat"
    EXPLAIN = "explain"
    MOMENT = "moment"
    UNCLEAR = "unclear"
    SKIP = "skip"


def classify_candidate_intent(text: str) -> CandidateIntent:
    """Classify common conversational controls while leaving ambiguous speech alone."""
    normalized = re.sub(r"[^\w\s']", " ", text.casefold())
    words = set(normalized.split())
    if words & {"skip", "pass"} and len(words) <= 8:
        return CandidateIntent.SKIP
    if (
        words & {"moment", "minute", "second", "think"}
        and len(words) <= 10
        and (words & {"give", "need", "let", "please", "me", "a", "time"})
    ):
        return CandidateIntent.MOMENT
    if words & {"understand", "confused", "unclear"}:
        return CandidateIntent.UNCLEAR
    if words & {"explain", "clarify", "meaning"} and words & {
        "question",
        "it",
        "that",
        "this",
        "again",
    }:
        return CandidateIntent.EXPLAIN
    if words & {"repeat", "restate", "hear"} and words & {
        "question",
        "again",
        "that",
        "it",
    }:
        return CandidateIntent.REPEAT
    return CandidateIntent.ANSWER


@dataclass
class CandidateTurnBuffer:
    """In-memory aggregation for finalized STT segments until a quiet window expires."""

    segments: list[str] | None = None
    event_ids: set[str] | None = None

    def __post_init__(self) -> None:
        self.segments = self.segments or []
        self.event_ids = self.event_ids or set()

    def add(self, text: str, event_id: str | None = None) -> bool:
        clean = text.strip()
        if not clean or (event_id and event_id in self.event_ids):
            return False
        if event_id:
            self.event_ids.add(event_id)
        self.segments.append(clean)
        return True

    def take(self) -> str:
        value = " ".join(self.segments or [])
        self.segments = []
        self.event_ids = set()
        return value


@dataclass(frozen=True)
class VoiceTurn:
    interview_id: UUID
    question_id: UUID | None
    question_text: str | None
    completed: bool
    summary_text: str | None = None
    disposition: TranscriptDisposition | None = None


class Speaker(Protocol):
    async def speak(self, text: str) -> None: ...


def _bound_room(
    session: Session,
    interview_id: UUID,
    room_name: str,
    participant_identity: str | None = None,
) -> tuple[InterviewSession, VoiceRoom]:
    room = session.scalar(
        select(VoiceRoom).where(
            VoiceRoom.interview_id == interview_id,
            VoiceRoom.room_name == room_name,
        )
    )
    if room is None:
        raise VoiceSessionError("Voice room is not associated with this interview")
    if participant_identity and room.candidate_identity != participant_identity:
        raise VoiceSessionError("Participant is not authorized for this interview")
    interview = session.get(InterviewSession, interview_id)
    if interview is None:
        raise VoiceSessionError("Interview session not found")
    return interview, room


def _turn_from_interview(interview: InterviewSession) -> VoiceTurn:
    if interview.status == InterviewStatus.COMPLETED:
        return VoiceTurn(
            interview_id=interview.id,
            question_id=None,
            question_text=None,
            completed=True,
            summary_text=interview.summary.summary if interview.summary else None,
        )
    unanswered = next(
        (
            question
            for question in sorted(interview.questions, key=lambda item: item.sequence)
            if question.answer is None and not question.skipped
        ),
        None,
    )
    return VoiceTurn(
        interview_id=interview.id,
        question_id=unanswered.id if unanswered else None,
        question_text=unanswered.text if unanswered else None,
        completed=False,
    )


def start_or_resume_voice_session(
    session: Session,
    interview_id: UUID,
    room_name: str,
    participant_identity: str,
    provider: AIProvider,
) -> VoiceTurn:
    """Recover entirely from durable state, including after a worker restart."""
    interview, room = _bound_room(
        session, interview_id, room_name, participant_identity
    )
    room.last_connected_at = utc_now()
    if interview.status == InterviewStatus.CREATED:
        interview = start_interview(session, interview_id, provider)
        if interview is None:
            raise VoiceSessionError("Interview session not found")
    session.flush()
    session.expire_all()
    loaded = get_history(session, interview_id)
    if loaded is None:
        raise VoiceSessionError("Interview session not found")
    return _turn_from_interview(loaded)


def _event_key(
    event_id: str | None,
    question_id: UUID,
    participant_identity: str,
    text: str,
) -> str:
    if event_id and event_id.strip():
        return event_id.strip()[:160]
    material = f"{question_id}:{participant_identity}:{text.strip()}".encode()
    return f"sha256:{hashlib.sha256(material).hexdigest()}"


def process_final_transcript(
    session: Session,
    interview_id: UUID,
    room_name: str,
    participant_identity: str,
    text: str,
    provider: AIProvider,
    *,
    event_id: str | None,
    is_final: bool,
) -> VoiceTurn:
    """Persist only a final transcript and submit it exactly once."""
    interview, room = _bound_room(
        session, interview_id, room_name, participant_identity
    )
    if not is_final:
        turn = _turn_from_interview(get_history(session, interview.id) or interview)
        return replace(turn, disposition=TranscriptDisposition.PARTIAL_IGNORED)
    transcript = text.strip()
    if not transcript:
        raise VoiceSessionError("Final transcript must not be blank")
    intent = classify_candidate_intent(transcript)
    if intent in {
        CandidateIntent.REPEAT,
        CandidateIntent.EXPLAIN,
        CandidateIntent.MOMENT,
        CandidateIntent.UNCLEAR,
    }:
        turn = _turn_from_interview(get_history(session, interview.id) or interview)
        return replace(turn, disposition=TranscriptDisposition.CLARIFICATION)
    if intent == CandidateIntent.SKIP:
        if interview.status != InterviewStatus.ACTIVE:
            turn = _turn_from_interview(get_history(session, interview.id) or interview)
            return replace(turn, disposition=TranscriptDisposition.DUPLICATE_IGNORED)
        _, question = current_question(session, interview.id)
        if question is None:
            raise VoiceSessionError("Interview has no current question")
        stable_event_id = _event_key(
            event_id, question.id, participant_identity, transcript
        )
        duplicate = session.scalar(
            select(VoiceTranscript).where(
                or_(
                    (VoiceTranscript.voice_room_id == room.id)
                    & (VoiceTranscript.event_id == stable_event_id),
                    VoiceTranscript.question_id == question.id,
                )
            )
        )
        if duplicate is not None:
            turn = _turn_from_interview(get_history(session, interview.id) or interview)
            return replace(turn, disposition=TranscriptDisposition.DUPLICATE_IGNORED)
        session.add(
            VoiceTranscript(
                voice_room_id=room.id,
                question_id=question.id,
                event_id=stable_event_id,
                participant_identity=participant_identity,
                text=transcript,
                status="processed",
                processed_at=utc_now(),
            )
        )
        result = skip_question(session, interview.id, question.id, provider)
        if result is None:
            raise VoiceSessionError("Interview session not found")
        session.flush()
        session.expire_all()
        loaded = get_history(session, interview.id)
        turn = _turn_from_interview(loaded)
        return replace(turn, disposition=TranscriptDisposition.SKIPPED)
    if interview.status != InterviewStatus.ACTIVE:
        if interview.status == InterviewStatus.COMPLETED:
            turn = _turn_from_interview(get_history(session, interview.id) or interview)
            return replace(turn, disposition=TranscriptDisposition.DUPLICATE_IGNORED)
        raise VoiceSessionError("Interview is not active")

    _, question = current_question(session, interview.id)
    if question is None:
        raise VoiceSessionError("Interview has no current question")
    stable_event_id = _event_key(
        event_id, question.id, participant_identity, transcript
    )
    existing = session.scalar(
        select(VoiceTranscript).where(
            or_(
                (
                    (VoiceTranscript.voice_room_id == room.id)
                    & (VoiceTranscript.event_id == stable_event_id)
                ),
                VoiceTranscript.question_id == question.id,
            )
        )
    )
    if existing is not None:
        turn = _turn_from_interview(get_history(session, interview.id) or interview)
        return replace(turn, disposition=TranscriptDisposition.DUPLICATE_IGNORED)

    record = VoiceTranscript(
        voice_room_id=room.id,
        question_id=question.id,
        event_id=stable_event_id,
        participant_identity=participant_identity,
        text=transcript,
        status="received",
    )
    session.add(record)
    try:
        session.flush()
    except IntegrityError:
        # A concurrent delivery won one of the database uniqueness guards.
        session.rollback()
        current, _ = _bound_room(session, interview_id, room_name, participant_identity)
        turn = _turn_from_interview(get_history(session, current.id) or current)
        return replace(turn, disposition=TranscriptDisposition.DUPLICATE_IGNORED)
    result = submit_answer(session, interview.id, question.id, transcript, provider)
    if result is None:
        raise VoiceSessionError("Interview session not found")
    record.status = "processed"
    record.processed_at = utc_now()
    session.flush()
    session.expire_all()
    loaded = get_history(session, interview.id)
    if loaded is None:
        raise VoiceSessionError("Interview session not found")
    turn = _turn_from_interview(loaded)
    return replace(turn, disposition=TranscriptDisposition.PROCESSED)


async def speak_turn(speaker: Speaker, turn: VoiceTurn) -> None:
    """Speak only text returned by the existing engine or persisted summary."""
    if turn.completed:
        message = "Interview complete."
        if turn.summary_text:
            message = f"{message} {turn.summary_text}"
        await speaker.speak(message)
    elif turn.question_text:
        await speaker.speak(turn.question_text)
