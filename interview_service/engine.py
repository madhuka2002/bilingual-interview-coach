"""Transactional orchestration for the text interview experience."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from interview_service.ai.base import (
    AIProvider,
    AIProviderResponseError,
    ConversationTurn,
    InterviewConfiguration,
)
from interview_service.models import (
    AnswerEvaluation,
    CandidateAnswer,
    InterviewQuestion,
    InterviewSession,
    InterviewStatus,
    InterviewSummary,
)
from interview_service.services import transition_interview


@dataclass
class InterviewConflictError(Exception):
    detail: str


@dataclass(frozen=True)
class AnswerCycleResult:
    answer: CandidateAnswer
    evaluation: AnswerEvaluation
    next_question: InterviewQuestion | None
    completed: bool


def _loaded_interview(session: Session, session_id: UUID) -> InterviewSession | None:
    return session.scalar(
        select(InterviewSession)
        .where(InterviewSession.id == session_id)
        .options(
            selectinload(InterviewSession.questions)
            .selectinload(InterviewQuestion.answer)
            .selectinload(CandidateAnswer.evaluation),
            selectinload(InterviewSession.summary),
        )
    )


def _history(interview: InterviewSession) -> list[ConversationTurn]:
    return [
        ConversationTurn(
            sequence=question.sequence,
            question=question.text,
            answer=question.answer.text if question.answer else None,
            score=(
                question.answer.evaluation.score
                if question.answer and question.answer.evaluation
                else None
            ),
            feedback=(
                question.answer.evaluation.feedback
                if question.answer and question.answer.evaluation
                else None
            ),
            skipped=question.skipped,
        )
        for question in sorted(interview.questions, key=lambda item: item.sequence)
    ]


def _configuration(interview: InterviewSession) -> InterviewConfiguration:
    return InterviewConfiguration(
        target_role=interview.target_role,
        experience_level=interview.experience_level,
        category=interview.category,
        difficulty=interview.difficulty,
        language=interview.language,
    )


def _validate_provider_strings(*values: str) -> None:
    if any(not value.strip() for value in values):
        raise AIProviderResponseError("Provider response contained blank text")


def start_interview(
    session: Session,
    interview_id: UUID,
    provider: AIProvider,
) -> InterviewSession | None:
    interview = _loaded_interview(session, interview_id)
    if interview is None:
        return None
    if interview.status == InterviewStatus.COMPLETED:
        raise InterviewConflictError(
            "Cannot transition interview session from completed to active"
        )
    if interview.status == InterviewStatus.ACTIVE:
        return interview

    generated = provider.generate_question(
        mode=interview.mode,
        language=interview.language,
        sequence=1,
        history=[],
        configuration=_configuration(interview),
    )
    _validate_provider_strings(generated.text, generated.topic)
    transitioned = transition_interview(
        session,
        interview.id,
        expected_status=InterviewStatus.CREATED,
        target_status=InterviewStatus.ACTIVE,
    )
    if transitioned is None:
        return None
    if not transitioned.questions:
        session.add(
            InterviewQuestion(
                interview_id=interview.id,
                sequence=1,
                text=generated.text.strip(),
                topic=generated.topic.strip(),
                provider=provider.name,
                model=provider.model,
            )
        )
        session.flush()
    return transitioned


def current_question(
    session: Session,
    interview_id: UUID,
) -> tuple[InterviewSession | None, InterviewQuestion | None]:
    interview = _loaded_interview(session, interview_id)
    if interview is None:
        return None, None
    if interview.status != InterviewStatus.ACTIVE:
        raise InterviewConflictError(
            f"Interview session is {interview.status}; an active session is required"
        )
    unanswered = [
        question
        for question in interview.questions
        if question.answer is None and not question.skipped
    ]
    if len(unanswered) != 1:
        raise InterviewConflictError("Interview session has no current question")
    return interview, unanswered[0]


def submit_answer(
    session: Session,
    interview_id: UUID,
    question_id: UUID,
    answer_text: str,
    provider: AIProvider,
) -> AnswerCycleResult | None:
    interview = _loaded_interview(session, interview_id)
    if interview is None:
        return None
    question = next(
        (item for item in interview.questions if item.id == question_id),
        None,
    )
    if question is None:
        raise InterviewConflictError("Question does not belong to this interview")
    if question.answer is not None or question.skipped:
        raise InterviewConflictError("An answer has already been submitted")
    if interview.status != InterviewStatus.ACTIVE:
        raise InterviewConflictError(
            f"Interview session is {interview.status}; "
            "answers require an active session"
        )
    current = max(interview.questions, key=lambda item: item.sequence, default=None)
    if current is None or current.id != question.id:
        raise InterviewConflictError("Only the current question can be answered")

    history = _history(interview)
    evaluation_result = provider.evaluate_answer(
        mode=interview.mode,
        language=interview.language,
        question=question.text,
        answer=answer_text,
        history=history[:-1],
        configuration=_configuration(interview),
    )
    _validate_provider_strings(
        evaluation_result.feedback,
        *evaluation_result.strengths,
        *evaluation_result.improvements,
    )
    completed_turn = ConversationTurn(
        sequence=question.sequence,
        question=question.text,
        answer=answer_text,
        score=evaluation_result.score,
        feedback=evaluation_result.feedback,
    )
    completed_history = [*history[:-1], completed_turn]

    generated_question = None
    summary_result = None
    if question.sequence >= interview.max_questions:
        summary_result = provider.summarize_interview(
            mode=interview.mode,
            language=interview.language,
            history=completed_history,
            configuration=_configuration(interview),
        )
        _validate_provider_strings(
            summary_result.summary,
            *summary_result.strengths,
            *summary_result.improvements,
        )
    else:
        generated_question = provider.generate_question(
            mode=interview.mode,
            language=interview.language,
            sequence=question.sequence + 1,
            history=completed_history,
            configuration=_configuration(interview),
        )
        _validate_provider_strings(generated_question.text, generated_question.topic)

    answer = CandidateAnswer(question=question, text=answer_text)
    evaluation = AnswerEvaluation(
        answer=answer,
        score=evaluation_result.score,
        feedback=evaluation_result.feedback.strip(),
        strengths=evaluation_result.strengths,
        improvements=evaluation_result.improvements,
        criteria=evaluation_result.criteria.model_dump(),
        learning_areas=evaluation_result.learning_areas,
        provider=provider.name,
        model=provider.model,
    )
    session.add_all([answer, evaluation])
    next_question = None
    if generated_question is not None:
        next_question = InterviewQuestion(
            interview=interview,
            sequence=question.sequence + 1,
            text=generated_question.text.strip(),
            topic=generated_question.topic.strip(),
            provider=provider.name,
            model=provider.model,
        )
        session.add(next_question)
    else:
        session.add(
            InterviewSummary(
                interview=interview,
                overall_score=summary_result.overall_score,
                summary=summary_result.summary.strip(),
                strengths=summary_result.strengths,
                improvements=summary_result.improvements,
                provider=provider.name,
                model=provider.model,
            )
        )
        transition_interview(
            session,
            interview.id,
            expected_status=InterviewStatus.ACTIVE,
            target_status=InterviewStatus.COMPLETED,
        )
    session.flush()
    return AnswerCycleResult(
        answer=answer,
        evaluation=evaluation,
        next_question=next_question,
        completed=summary_result is not None,
    )


def skip_question(
    session: Session, interview_id: UUID, question_id: UUID, provider: AIProvider
) -> InterviewSession | None:
    """Record a skipped question without manufacturing candidate speech."""
    interview = _loaded_interview(session, interview_id)
    if interview is None:
        return None
    question = next(
        (item for item in interview.questions if item.id == question_id), None
    )
    if question is None or question.answer is not None or question.skipped:
        raise InterviewConflictError("Question cannot be skipped in its current state")
    if interview.status != InterviewStatus.ACTIVE or question.sequence != max(
        item.sequence for item in interview.questions
    ):
        raise InterviewConflictError("Only the current active question can be skipped")
    question.skipped = True
    history = _history(interview)
    if question.sequence >= interview.max_questions:
        result = provider.summarize_interview(
            mode=interview.mode,
            language=interview.language,
            history=history,
            configuration=_configuration(interview),
        )
        session.add(
            InterviewSummary(
                interview=interview,
                overall_score=result.overall_score,
                summary=result.summary.strip(),
                strengths=result.strengths,
                improvements=result.improvements,
                provider=provider.name,
                model=provider.model,
            )
        )
        transition_interview(
            session,
            interview.id,
            expected_status=InterviewStatus.ACTIVE,
            target_status=InterviewStatus.COMPLETED,
        )
    else:
        generated = provider.generate_question(
            mode=interview.mode,
            language=interview.language,
            sequence=question.sequence + 1,
            history=history,
            configuration=_configuration(interview),
        )
        session.add(
            InterviewQuestion(
                interview=interview,
                sequence=question.sequence + 1,
                text=generated.text.strip(),
                topic=generated.topic.strip(),
                provider=provider.name,
                model=provider.model,
            )
        )
    session.flush()
    return interview


def complete_interview(
    session: Session,
    interview_id: UUID,
    provider: AIProvider,
) -> InterviewSession | None:
    interview = _loaded_interview(session, interview_id)
    if interview is None:
        return None
    if interview.status == InterviewStatus.COMPLETED:
        return interview
    if interview.status != InterviewStatus.ACTIVE:
        raise InterviewConflictError(
            f"Cannot transition interview session from {interview.status} to completed"
        )
    summary_result = provider.summarize_interview(
        mode=interview.mode,
        language=interview.language,
        history=_history(interview),
        configuration=_configuration(interview),
    )
    _validate_provider_strings(
        summary_result.summary,
        *summary_result.strengths,
        *summary_result.improvements,
    )
    session.add(
        InterviewSummary(
            interview=interview,
            overall_score=summary_result.overall_score,
            summary=summary_result.summary.strip(),
            strengths=summary_result.strengths,
            improvements=summary_result.improvements,
            provider=provider.name,
            model=provider.model,
        )
    )
    transitioned = transition_interview(
        session,
        interview.id,
        expected_status=InterviewStatus.ACTIVE,
        target_status=InterviewStatus.COMPLETED,
    )
    session.flush()
    return transitioned


def get_history(session: Session, interview_id: UUID) -> InterviewSession | None:
    return _loaded_interview(session, interview_id)


def get_feedback(
    session: Session,
    interview_id: UUID,
) -> tuple[InterviewSession | None, list[AnswerEvaluation]]:
    """Return persisted evaluations without depending on an HTTP transport."""
    interview = _loaded_interview(session, interview_id)
    if interview is None:
        return None, []
    evaluations = [
        question.answer.evaluation
        for question in interview.questions
        if question.answer and question.answer.evaluation
    ]
    return interview, evaluations
