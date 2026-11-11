"""Deterministic AI provider for tests and local demonstrations."""

from interview_service.ai.base import (
    ConversationTurn,
    EvaluationResult,
    QuestionResult,
    SummaryResult,
)


class MockAIProvider:
    name = "mock"
    model = "deterministic-interview-v1"

    _questions = {
        "en": [
            ("background", "Tell me about your professional background."),
            ("problem solving", "Describe a difficult problem you solved."),
            ("collaboration", "How do you handle disagreement in a team?"),
            ("learning", "Tell me about a skill you learned recently."),
            ("goals", "What would success in your next role look like?"),
        ],
        "si": [
            ("පසුබිම", "ඔබගේ වෘත්තීය පසුබිම ගැන කියන්න."),
            ("ගැටලු විසඳීම", "ඔබ විසඳූ දුෂ්කර ගැටලුවක් විස්තර කරන්න."),
            ("සහයෝගීතාව", "කණ්ඩායමක මතභේදයක් ඔබ හසුරුවන්නේ කෙසේද?"),
            ("ඉගෙනීම", "ඔබ මෑතකදී ඉගෙනගත් කුසලතාවක් ගැන කියන්න."),
            ("ඉලක්ක", "ඔබගේ මීළඟ භූමිකාවේ සාර්ථකත්වය කෙසේ පෙනේද?"),
        ],
    }

    def generate_question(
        self,
        *,
        mode: str,
        language: str,
        sequence: int,
        history: list[ConversationTurn],
    ) -> QuestionResult:
        questions = self._questions[language]
        topic, text = questions[(sequence - 1) % len(questions)]
        if mode == "career_coach":
            text = (
                f"Career coaching question: {text}"
                if language == "en"
                else f"වෘත්තීය උපදේශන ප්‍රශ්නය: {text}"
            )
        return QuestionResult(text=text, topic=topic)

    def evaluate_answer(
        self,
        *,
        mode: str,
        language: str,
        question: str,
        answer: str,
        history: list[ConversationTurn],
    ) -> EvaluationResult:
        score = min(95, 55 + len(answer.split()) * 2)
        if language == "si":
            return EvaluationResult(
                score=score,
                feedback="පිළිතුර පැහැදිලිය; නිශ්චිත උදාහරණයක් තවත් එක් කරන්න.",
                strengths=["ප්‍රශ්නයට සෘජුව පිළිතුරු දී ඇත"],
                improvements=["මැනිය හැකි ප්‍රතිඵලයක් එක් කරන්න"],
            )
        return EvaluationResult(
            score=score,
            feedback="The answer is clear; add one more specific example.",
            strengths=["Directly addresses the question"],
            improvements=["Include a measurable outcome"],
        )

    def summarize_interview(
        self,
        *,
        mode: str,
        language: str,
        history: list[ConversationTurn],
    ) -> SummaryResult:
        scores = [turn.score for turn in history if turn.score is not None]
        overall_score = round(sum(scores) / len(scores)) if scores else 0
        if language == "si":
            return SummaryResult(
                overall_score=overall_score,
                summary="සම්මුඛ පරීක්ෂණය අවසන්. පිළිතුරු පැහැදිලි සහ අදාළ විය.",
                strengths=["පැහැදිලි සන්නිවේදනය"],
                improvements=["තවත් නිශ්චිත ප්‍රතිඵල එක් කරන්න"],
            )
        return SummaryResult(
            overall_score=overall_score,
            summary="Interview complete. The answers were clear and relevant.",
            strengths=["Clear communication"],
            improvements=["Add more specific, measurable outcomes"],
        )
