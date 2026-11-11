"""Small event-loop-local guard for voice conversation transitions."""

from enum import StrEnum


class ConversationState(StrEnum):
    INTERVIEWER_SPEAKING = "interviewer_speaking"
    CANDIDATE_SPEAKING = "candidate_speaking"
    ANSWER_PROCESSING = "answer_processing"
    CLARIFICATION = "clarification"
    COMPLETED = "completed"
    FAILED = "failed"


class ConversationStateError(RuntimeError):
    """Raised when a worker event is invalid for the current conversation state."""


class ConversationStateController:
    """Enforce legal voice transitions on the worker's single asyncio loop."""

    _ALLOWED = {
        ConversationState.INTERVIEWER_SPEAKING: {
            ConversationState.CANDIDATE_SPEAKING,
            ConversationState.CLARIFICATION,
            ConversationState.COMPLETED,
            ConversationState.FAILED,
        },
        ConversationState.CANDIDATE_SPEAKING: {
            ConversationState.ANSWER_PROCESSING,
            ConversationState.INTERVIEWER_SPEAKING,
            ConversationState.COMPLETED,
            ConversationState.FAILED,
        },
        ConversationState.ANSWER_PROCESSING: {
            ConversationState.CANDIDATE_SPEAKING,
            ConversationState.INTERVIEWER_SPEAKING,
            ConversationState.CLARIFICATION,
            ConversationState.COMPLETED,
            ConversationState.FAILED,
        },
        ConversationState.CLARIFICATION: {
            ConversationState.ANSWER_PROCESSING,
            ConversationState.INTERVIEWER_SPEAKING,
            ConversationState.CANDIDATE_SPEAKING,
            ConversationState.COMPLETED,
            ConversationState.FAILED,
        },
        ConversationState.COMPLETED: set(),
        ConversationState.FAILED: set(),
    }

    def __init__(self, initial: ConversationState) -> None:
        self.state = initial
        self._delivered_question_ids: set[str] = set()
        self._submitted_question_ids: set[str] = set()

    def transition(self, target: ConversationState) -> None:
        if target == self.state:
            return
        if target not in self._ALLOWED[self.state]:
            raise ConversationStateError(
                f"Invalid conversation transition: {self.state} -> {target}"
            )
        self.state = target

    def can_accept_answer(self) -> bool:
        return self.state in {
            ConversationState.CANDIDATE_SPEAKING,
            ConversationState.CLARIFICATION,
        }

    def mark_question_delivered(self, question_id: str) -> bool:
        if self.state != ConversationState.INTERVIEWER_SPEAKING:
            raise ConversationStateError(
                "Question delivery requires interviewer playback"
            )
        if question_id in self._delivered_question_ids:
            return False
        self._delivered_question_ids.add(question_id)
        return True

    def mark_submission(self, question_id: str) -> bool:
        if not self.can_accept_answer():
            raise ConversationStateError(
                "Answer submission is not allowed in this state"
            )
        if question_id in self._submitted_question_ids:
            return False
        self._submitted_question_ids.add(question_id)
        return True
