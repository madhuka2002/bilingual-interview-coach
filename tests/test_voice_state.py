"""Deterministic guards for worker conversation transitions."""

import pytest

from interview_service.voice.state import (
    ConversationState,
    ConversationStateController,
    ConversationStateError,
)


def test_question_delivery_and_submission_are_once_per_key() -> None:
    controller = ConversationStateController(ConversationState.INTERVIEWER_SPEAKING)
    assert controller.mark_question_delivered("q1")
    assert not controller.mark_question_delivered("q1")
    controller.transition(ConversationState.CANDIDATE_SPEAKING)
    assert controller.mark_submission("q1")
    assert not controller.mark_submission("q1")


def test_playback_and_terminal_states_reject_answer_submission() -> None:
    controller = ConversationStateController(ConversationState.INTERVIEWER_SPEAKING)
    assert not controller.can_accept_answer()
    with pytest.raises(ConversationStateError, match="not allowed"):
        controller.mark_submission("q1")
    controller.transition(ConversationState.COMPLETED)
    with pytest.raises(ConversationStateError, match="Invalid conversation"):
        controller.transition(ConversationState.CANDIDATE_SPEAKING)


def test_processing_can_return_to_playback_then_accept_candidate_after_tts() -> None:
    controller = ConversationStateController(ConversationState.CANDIDATE_SPEAKING)
    controller.transition(ConversationState.ANSWER_PROCESSING)
    controller.transition(ConversationState.INTERVIEWER_SPEAKING)
    assert not controller.can_accept_answer()
    controller.transition(ConversationState.CANDIDATE_SPEAKING)
    assert controller.can_accept_answer()
