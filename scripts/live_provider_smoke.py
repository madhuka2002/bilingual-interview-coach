"""Explicitly enabled, short paid-provider interview smoke test."""

import argparse
import json
import os
from typing import Any

from interview_service.ai.base import ConversationTurn, InterviewConfiguration
from interview_service.ai.openai import OpenAIProvider

CONFIRMATION = "I_CONFIRM_PAID_API_CALL"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one short, paid OpenAI interview flow."
    )
    parser.add_argument("--language", choices=("en", "si"), required=True)
    parser.add_argument("--confirm-paid-call", required=True)
    return parser.parse_args()


def require_explicit_enablement(args: argparse.Namespace) -> None:
    if os.getenv("LIVE_PROVIDER_SMOKE_ENABLED") != "1":
        raise SystemExit("Set LIVE_PROVIDER_SMOKE_ENABLED=1 to enable paid calls.")
    if args.confirm_paid_call != CONFIRMATION:
        raise SystemExit(f"Pass --confirm-paid-call {CONFIRMATION} to continue.")
    if os.getenv("AI_PROVIDER", "mock").lower() != "openai":
        raise SystemExit("Set AI_PROVIDER=openai explicitly; default remains mock.")


def validate_language(text: str, language: str) -> None:
    has_sinhala = any("\u0d80" <= character <= "\u0dff" for character in text)
    if language == "si" and not has_sinhala:
        raise RuntimeError("Expected Sinhala text but none was detected.")
    if language == "en" and has_sinhala:
        raise RuntimeError("Expected English text but Sinhala text was detected.")


def record_usage(records: list[dict[str, Any]], provider: OpenAIProvider) -> None:
    if provider.last_usage is not None:
        records.append(provider.last_usage)


def main() -> None:
    args = parse_args()
    require_explicit_enablement(args)
    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_MODEL", "")
    provider = OpenAIProvider(
        api_key=api_key,
        model=model,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        timeout_seconds=float(os.getenv("AI_TIMEOUT_SECONDS", "20")),
        max_retries=int(os.getenv("AI_MAX_RETRIES", "1")),
    )
    config = InterviewConfiguration(
        target_role="Software Engineer",
        experience_level="mid",
        category="mixed",
        difficulty="intermediate",
        language=args.language,
    )
    usage_records: list[dict[str, Any]] = []
    question = provider.generate_question(
        mode="mock_interview",
        language=args.language,
        sequence=1,
        history=[],
        configuration=config,
    )
    record_usage(usage_records, provider)
    validate_language(question.text, args.language)
    answer = (
        "මම REST API එකක් නිර්මාණය කර latency සියයට 20කින් අඩු කළා."
        if args.language == "si"
        else "I designed a REST API and reduced latency by 20 percent."
    )
    evaluation = provider.evaluate_answer(
        mode="mock_interview",
        language=args.language,
        question=question.text,
        answer=answer,
        history=[],
        configuration=config,
    )
    record_usage(usage_records, provider)
    validate_language(evaluation.feedback, args.language)
    turn = ConversationTurn(
        sequence=1,
        question=question.text,
        answer=answer,
        score=evaluation.score,
        feedback=evaluation.feedback,
    )
    summary = provider.summarize_interview(
        mode="mock_interview",
        language=args.language,
        history=[turn],
        configuration=config,
    )
    record_usage(usage_records, provider)
    validate_language(summary.summary, args.language)
    print(
        json.dumps(
            {
                "status": "passed",
                "language": args.language,
                "model": provider.model,
                "question": question.text,
                "score": evaluation.score,
                "usage": usage_records or "not reported by provider",
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
