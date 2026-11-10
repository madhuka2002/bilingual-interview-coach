"""Transactional interview lifecycle operations."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from interview_service.models import InterviewSession, InterviewStatus, utc_now


@dataclass(frozen=True)
class InvalidTransitionError(Exception):
    current_status: str
    requested_status: str


def get_interview(session: Session, session_id: UUID) -> InterviewSession | None:
    return session.get(InterviewSession, session_id)


def transition_interview(
    session: Session,
    session_id: UUID,
    *,
    expected_status: InterviewStatus,
    target_status: InterviewStatus,
) -> InterviewSession | None:
    """Atomically transition a session, returning the idempotent result."""
    transition_time = utc_now()
    values: dict[str, object] = {
        "status": target_status,
        "updated_at": transition_time,
    }
    if target_status is InterviewStatus.ACTIVE:
        values["started_at"] = transition_time
    elif target_status is InterviewStatus.COMPLETED:
        values["completed_at"] = transition_time

    result = session.execute(
        update(InterviewSession)
        .where(
            InterviewSession.id == session_id,
            InterviewSession.status == expected_status,
        )
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 1:
        session.flush()
        return get_interview(session, session_id)

    current = get_interview(session, session_id)
    if current is None:
        return None
    if current.status == target_status:
        return current
    raise InvalidTransitionError(current.status, target_status)
