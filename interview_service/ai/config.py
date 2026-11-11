"""Environment-based provider construction."""

import os
from functools import lru_cache

from interview_service.ai.base import AIProvider, AIProviderUnavailableError
from interview_service.ai.mock import MockAIProvider
from interview_service.ai.openai import OpenAIProvider


def _number(name: str, default: str, cast: type[float] | type[int]) -> float | int:
    try:
        value = cast(os.getenv(name, default))
    except ValueError as error:
        raise AIProviderUnavailableError(f"Invalid {name} configuration") from error
    if value < 0:
        raise AIProviderUnavailableError(f"Invalid {name} configuration")
    return value


@lru_cache
def get_ai_provider() -> AIProvider:
    provider_name = os.getenv("AI_PROVIDER", "mock").strip().lower()
    if provider_name == "mock":
        return MockAIProvider()
    if provider_name == "openai":
        api_key = os.getenv("OPENAI_API_KEY", "")
        model = os.getenv("OPENAI_MODEL", "")
        return OpenAIProvider(
            api_key=api_key,
            model=model,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            timeout_seconds=float(_number("AI_TIMEOUT_SECONDS", "20", float)),
            max_retries=int(_number("AI_MAX_RETRIES", "1", int)),
        )
    raise AIProviderUnavailableError("Unsupported AI provider")


def get_question_limit() -> int:
    value = int(_number("AI_QUESTION_LIMIT", "5", int))
    if not 1 <= value <= 20:
        raise AIProviderUnavailableError("AI_QUESTION_LIMIT must be between 1 and 20")
    return value
