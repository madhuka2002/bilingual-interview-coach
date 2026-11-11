"""Versioned, provider-neutral prompts for bilingual interview intelligence."""

from interview_service.ai.base import ConversationTurn, InterviewConfiguration

PROMPT_VERSION = "bic-006-v1"


def language_instruction(language: str) -> str:
    if language == "si":
        return (
            "Use natural Sinhala for questions and feedback, while retaining standard "
            "English technical terms (for example API, database, CI/CD) when that is "
            "clearer than an artificial translation."
        )
    return "Use natural, professional English for questions and feedback."


def configuration_text(configuration: InterviewConfiguration) -> str:
    return (
        f"Target role: {configuration.target_role}. "
        f"Experience level: {configuration.experience_level}. "
        f"Category: {configuration.category}. "
        f"Difficulty: {configuration.difficulty}. "
        f"{language_instruction(configuration.language)}"
    )


def history_text(history: list[ConversationTurn]) -> str:
    if not history:
        return "No earlier turns."
    return "\n".join(
        f"{turn.sequence}. Q: {turn.question}\n"
        f"A: {turn.answer or '[unanswered]'}\n"
        f"Score: {turn.score if turn.score is not None else '[not evaluated]'}\n"
        f"Feedback: {turn.feedback or '[none]'}"
        for turn in history
    )


def question_prompt(
    configuration: InterviewConfiguration,
    sequence: int,
    history: list[ConversationTurn],
) -> str:
    follow_up = (
        "Use the candidate's previous answer to ask a relevant follow-up when useful."
        if history
        else "Begin with a realistic opening question."
    )
    return (
        f"Prompt version: {PROMPT_VERSION}. Generate exactly one concise interview "
        f"question as JSON. {configuration_text(configuration)} Sequence: {sequence}. "
        f"{follow_up} Do not repeat earlier questions.\nHistory:\n"
        f"{history_text(history)}"
    )


def evaluation_prompt(
    configuration: InterviewConfiguration,
    question: str,
    answer: str,
    history: list[ConversationTurn],
) -> str:
    return (
        f"Prompt version: {PROMPT_VERSION}. Evaluate the answer constructively as "
        f"JSON. {configuration_text(configuration)} Score relevance, "
        "technical_accuracy, "
        "clarity, completeness, and communication_quality from 0 to 20 each; score "
        "must be their sum. For non-technical questions, technical_accuracy means "
        "factual and contextual accuracy. Avoid claims about employability or broad "
        f"competence. Question: {question}\nAnswer: {answer}\nEarlier history:\n"
        f"{history_text(history)}"
    )


def summary_prompt(
    configuration: InterviewConfiguration,
    history: list[ConversationTurn],
) -> str:
    return (
        f"Prompt version: {PROMPT_VERSION}. Produce a structured, constructive final "
        f"summary as JSON. {configuration_text(configuration)} Base it only on the "
        "recorded answers and evaluations. Do not make employability claims.\n"
        "History:\n"
        f"{history_text(history)}"
    )
