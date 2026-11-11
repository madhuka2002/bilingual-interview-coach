"""Server-side LiveKit room association and candidate token issuance."""

import json
from datetime import timedelta
from uuid import uuid4

from livekit import api
from sqlalchemy import select
from sqlalchemy.orm import Session

from interview_service.models import InterviewSession, VoiceRoom
from interview_service.voice.config import LiveKitSettings


def get_or_create_voice_room(
    session: Session, interview: InterviewSession
) -> VoiceRoom:
    room = session.scalar(
        select(VoiceRoom).where(VoiceRoom.interview_id == interview.id)
    )
    if room is not None:
        return room
    opaque = uuid4().hex
    room = VoiceRoom(
        interview_id=interview.id,
        room_name=f"bic-{opaque}",
        candidate_identity=f"candidate-{uuid4().hex}",
    )
    session.add(room)
    session.flush()
    return room


def issue_candidate_token(
    session: Session,
    interview: InterviewSession,
    settings: LiveKitSettings,
) -> tuple[VoiceRoom, str]:
    room = get_or_create_voice_room(session, interview)
    dispatch_metadata = json.dumps(
        {"interview_id": str(interview.id), "room_name": room.room_name},
        separators=(",", ":"),
    )
    grants = api.VideoGrants(
        room_join=True,
        room=room.room_name,
        can_publish=True,
        can_subscribe=True,
        can_publish_data=False,
        can_publish_sources=["microphone"],
        can_update_own_metadata=False,
        room_admin=False,
    )
    room_config = api.RoomConfiguration(
        name=room.room_name,
        empty_timeout=60,
        departure_timeout=60,
        max_participants=2,
        agents=[
            api.RoomAgentDispatch(
                agent_name=settings.agent_name,
                metadata=dispatch_metadata,
            )
        ],
    )
    token = (
        api.AccessToken(settings.api_key, settings.api_secret)
        .with_identity(room.candidate_identity)
        .with_name("Candidate")
        .with_kind("standard")
        .with_metadata(dispatch_metadata)
        .with_grants(grants)
        .with_room_config(room_config)
        .with_ttl(timedelta(seconds=settings.token_ttl_seconds))
        .to_jwt()
    )
    return room, token
