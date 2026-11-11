"""OpenAI Responses API adapter using documented HTTP contracts."""

import json
import time
from collections.abc import Callable
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from interview_service.ai.base import (
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    ConversationTurn,
    EvaluationResult,
    InterviewConfiguration,
    QuestionResult,
    SummaryResult,
)
from interview_service.ai.prompts import (
    evaluation_prompt,
    question_prompt,
    summary_prompt,
)

ResultModel = TypeVar("ResultModel", bound=BaseModel)


class OpenAIProvider:
    """Call the Responses API with strict structured output and safe retries."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 20.0,
        max_retries: int = 1,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key or not model:
            raise AIProviderUnavailableError("OpenAI provider is not configured")
        self.model = model
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._transport = transport
        self._sleep = sleep
        self.last_usage: dict[str, Any] | None = None

    def generate_question(
        self,
        *,
        mode: str,
        language: str,
        sequence: int,
        history: list[ConversationTurn],
        configuration: InterviewConfiguration,
    ) -> QuestionResult:
        return self._request(
            QuestionResult,
            "interview_question",
            question_prompt(configuration, sequence, history),
        )

    def evaluate_answer(
        self,
        *,
        mode: str,
        language: str,
        question: str,
        answer: str,
        history: list[ConversationTurn],
        configuration: InterviewConfiguration,
    ) -> EvaluationResult:
        return self._request(
            EvaluationResult,
            "answer_evaluation",
            evaluation_prompt(configuration, question, answer, history),
        )

    def summarize_interview(
        self,
        *,
        mode: str,
        language: str,
        history: list[ConversationTurn],
        configuration: InterviewConfiguration,
    ) -> SummaryResult:
        return self._request(
            SummaryResult,
            "interview_summary",
            summary_prompt(configuration, history),
        )

    def _request(
        self,
        result_type: type[ResultModel],
        schema_name: str,
        prompt: str,
    ) -> ResultModel:
        body = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": "You are a bilingual professional interview coach.",
                },
                {"role": "user", "content": prompt},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": schema_name,
                    "strict": True,
                    "schema": result_type.model_json_schema(),
                }
            },
        }
        response_data = self._post_with_retries(body)
        usage = response_data.get("usage")
        self.last_usage = usage if isinstance(usage, dict) else None
        try:
            if response_data.get("status") != "completed":
                raise AIProviderResponseError("Provider response was incomplete")
            output_text = self._extract_output_text(response_data)
            return result_type.model_validate_json(output_text)
        except (KeyError, TypeError, json.JSONDecodeError, ValidationError) as error:
            raise AIProviderResponseError("Provider response was malformed") from error

    def _post_with_retries(self, body: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(self._max_retries + 1):
            try:
                with httpx.Client(
                    timeout=self._timeout_seconds,
                    transport=self._transport,
                ) as client:
                    response = client.post(
                        f"{self._base_url}/responses",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        json=body,
                    )
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self._max_retries:
                        self._sleep(0.25 * (2**attempt))
                        continue
                    raise AIProviderResponseError("Provider request failed")
                if response.status_code >= 400:
                    raise AIProviderResponseError("Provider rejected the request")
                data = response.json()
                if not isinstance(data, dict):
                    raise AIProviderResponseError("Provider response was malformed")
                return data
            except httpx.TimeoutException as error:
                if attempt < self._max_retries:
                    self._sleep(0.25 * (2**attempt))
                    continue
                raise AIProviderTimeoutError("Provider request timed out") from error
            except httpx.RequestError as error:
                if attempt < self._max_retries:
                    self._sleep(0.25 * (2**attempt))
                    continue
                raise AIProviderUnavailableError("Provider is unavailable") from error
            except ValueError as error:
                raise AIProviderResponseError(
                    "Provider response was malformed"
                ) from error
        raise AIProviderResponseError("Provider request failed")

    @staticmethod
    def _extract_output_text(response_data: dict[str, Any]) -> str:
        for item in response_data["output"]:
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    return content["text"]
        raise AIProviderResponseError("Provider response did not contain output text")
