"""BIC-006 configuration, bilingual prompting, and rubric regression tests."""

from argparse import Namespace
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from interview_service.ai.base import (
    ConversationTurn,
    CriterionScores,
    EvaluationResult,
    InterviewConfiguration,
)
from interview_service.ai.mock import MockAIProvider
from interview_service.ai.prompts import evaluation_prompt, question_prompt
from interview_service.main import app
from interview_service.models import InterviewSession
from scripts.live_provider_smoke import require_explicit_enablement


def configuration(language: str = "en") -> InterviewConfiguration:
    return InterviewConfiguration(
        target_role="Platform Engineer",
        experience_level="senior",
        category="technical",
        difficulty="advanced",
        language=language,
    )


@pytest.mark.anyio
async def test_configured_session_is_persisted_and_retrievable(
    database_engine: Engine,
) -> None:
    payload = {
        "mode": "mock_interview",
        "language": "si",
        "target_role": "Platform Engineer",
        "experience_level": "senior",
        "category": "technical",
        "difficulty": "advanced",
        "question_limit": 2,
    }
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/v1/interviews", json=payload)
        config = await client.get(
            f"/v1/interviews/{created.json()['id']}/configuration"
        )

    assert created.status_code == 201
    assert set(created.json()) == {"id", "mode", "language", "status"}
    assert config.json() == {
        "interview_id": created.json()["id"],
        "target_role": "Platform Engineer",
        "experience_level": "senior",
        "category": "technical",
        "difficulty": "advanced",
        "preferred_language": "si",
        "question_limit": 2,
    }
    with Session(database_engine) as session:
        persisted = session.get(InterviewSession, UUID(created.json()["id"]))
        assert persisted is not None
        assert persisted.target_role == "Platform Engineer"
        assert persisted.max_questions == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    "override",
    [
        {"target_role": " "},
        {"experience_level": "principal"},
        {"category": "sales"},
        {"difficulty": "impossible"},
        {"question_limit": 0},
        {"question_limit": 21},
    ],
)
async def test_invalid_configuration_is_rejected(override: dict) -> None:
    payload = {"mode": "mock_interview", "language": "en", **override}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/v1/interviews", json=payload)
    assert response.status_code == 422


def test_versioned_prompts_cover_english_sinhala_and_technical_terms() -> None:
    english = question_prompt(configuration("en"), 1, [])
    sinhala = question_prompt(configuration("si"), 1, [])
    evaluation = evaluation_prompt(configuration("si"), "API?", "REST API", [])

    assert "bic-006-v1" in english
    assert "Platform Engineer" in english
    assert "professional English" in english
    assert "natural Sinhala" in sinhala
    assert "API, database, CI/CD" in sinhala
    assert "technical_accuracy" in evaluation
    assert "employability" in evaluation


def test_rubric_score_must_equal_five_criteria() -> None:
    criteria = CriterionScores(
        relevance=10,
        technical_accuracy=11,
        clarity=12,
        completeness=13,
        communication_quality=14,
    )
    with pytest.raises(ValidationError):
        EvaluationResult(
            score=99,
            criteria=criteria,
            feedback="Useful feedback",
            strengths=["Relevant"],
            improvements=["More evidence"],
            learning_areas=["System design"],
        )


def test_mock_rubric_is_deterministic_and_follow_up_uses_context() -> None:
    provider = MockAIProvider()
    config = configuration("en")
    history = [
        ConversationTurn(
            sequence=1,
            question="Describe a migration.",
            answer="I migrated 12 services with no downtime.",
            score=75,
            feedback="Good evidence.",
        )
    ]
    first = provider.evaluate_answer(
        mode="mock_interview",
        language="en",
        question="Describe a migration.",
        answer=history[0].answer or "",
        history=[],
        configuration=config,
    )
    second = provider.evaluate_answer(
        mode="mock_interview",
        language="en",
        question="Describe a migration.",
        answer=history[0].answer or "",
        history=[],
        configuration=config,
    )
    follow_up = provider.generate_question(
        mode="mock_interview",
        language="en",
        sequence=2,
        history=history,
        configuration=config,
    )

    assert first == second
    assert first.score == first.criteria.total
    assert "Following up" in follow_up.text


def test_sinhala_mock_keeps_common_english_technical_terminology() -> None:
    provider = MockAIProvider()
    result = provider.generate_question(
        mode="mock_interview",
        language="si",
        sequence=2,
        history=[ConversationTurn(sequence=1, question="Q", answer="A")],
        configuration=configuration("si"),
    )
    assert "API" in result.text
    assert any("\u0d80" <= char <= "\u0dff" for char in result.text)


def test_live_smoke_is_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LIVE_PROVIDER_SMOKE_ENABLED", raising=False)
    monkeypatch.setenv("AI_PROVIDER", "mock")
    with pytest.raises(SystemExit, match="LIVE_PROVIDER_SMOKE_ENABLED"):
        require_explicit_enablement(
            Namespace(confirm_paid_call="I_CONFIRM_PAID_API_CALL")
        )
