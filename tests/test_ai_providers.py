"""Tests for provider configuration and real-adapter response handling."""

import json

import httpx
import pytest

from interview_service.ai.base import (
    AIProviderResponseError,
    AIProviderTimeoutError,
    InterviewConfiguration,
)
from interview_service.ai.openai import OpenAIProvider

CONFIGURATION = InterviewConfiguration(
    target_role="Software Engineer",
    experience_level="mid",
    category="mixed",
    difficulty="intermediate",
    language="en",
)


def completed_response(payload: dict) -> dict:
    return {
        "status": "completed",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": json.dumps(payload)}],
            }
        ],
    }


def test_openai_adapter_uses_configured_model_and_validates_output() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url == "https://provider.example/v1/responses"
        assert request.headers["authorization"] == "Bearer test-secret"
        assert body["model"] == "operator-selected-model"
        assert body["text"]["format"]["type"] == "json_schema"
        return httpx.Response(
            200,
            json=completed_response({"text": "Question?", "topic": "topic"}),
        )

    provider = OpenAIProvider(
        api_key="test-secret",
        model="operator-selected-model",
        base_url="https://provider.example/v1",
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )

    result = provider.generate_question(
        mode="mock_interview",
        language="en",
        sequence=1,
        history=[],
        configuration=CONFIGURATION,
    )

    assert result.text == "Question?"
    assert provider.model == "operator-selected-model"


def test_openai_adapter_retries_timeout_without_paid_calls() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("private", request=request)

    provider = OpenAIProvider(
        api_key="test-secret",
        model="configured-model",
        max_retries=1,
        transport=httpx.MockTransport(handler),
        sleep=lambda _: None,
    )

    with pytest.raises(AIProviderTimeoutError):
        provider.generate_question(
            mode="mock_interview",
            language="en",
            sequence=1,
            history=[],
            configuration=CONFIGURATION,
        )
    assert calls == 2


@pytest.mark.parametrize(
    "response_payload",
    [
        {"status": "completed", "output": []},
        completed_response({"text": "missing topic"}),
        completed_response({"text": "Question?", "topic": "topic", "extra": 1}),
    ],
)
def test_openai_adapter_rejects_malformed_responses(response_payload: dict) -> None:
    provider = OpenAIProvider(
        api_key="test-secret",
        model="configured-model",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=response_payload)
        ),
        sleep=lambda _: None,
    )

    with pytest.raises(AIProviderResponseError):
        provider.generate_question(
            mode="mock_interview",
            language="en",
            sequence=1,
            history=[],
            configuration=CONFIGURATION,
        )
