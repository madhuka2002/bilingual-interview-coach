"""Deterministic bilingual provider for tests and local demonstrations."""

from interview_service.ai.base import (
    ConversationTurn,
    CriterionScores,
    EvaluationResult,
    InterviewConfiguration,
    QuestionResult,
    SummaryResult,
)


class MockAIProvider:
    name = "mock"
    model = "deterministic-interview-v2"

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
        configuration: InterviewConfiguration,
    ) -> QuestionResult:
        topic, text = self._questions[language][(sequence - 1) % 5]
        if sequence == 1 and configuration.target_role != "Software Engineer":
            if language == "si":
                text = f"{configuration.target_role} භූමිකාවට අදාළ ඔබගේ පසුබිම ගැන කියන්න."
            else:
                text = (
                    f"Tell me about your background relevant to the "
                    f"{configuration.target_role} role."
                )
        elif history and history[-1].answer:
            if language == "si":
                text = (
                    f"ඔබගේ පෙර පිළිතුර මත පදනම්ව, {text} "
                    "API වැනි technical terms අවශ්‍ය පරිදි භාවිත කරන්න."
                )
            else:
                text = f"Following up on your previous answer: {text}"
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
        configuration: InterviewConfiguration,
    ) -> EvaluationResult:
        word_count = len(answer.split())
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "to",
            "of",
            "and",
            "how",
            "what",
            "you",
            "your",
            "i",
            "it",
            "do",
            "can",
            "about",
        }
        question_terms = {
            token.strip(".,?!:;()[]{}'").casefold()
            for token in question.split()
            if len(token.strip(".,?!:;()[]{}'")) > 2
            and token.strip(".,?!:;()[]{}'").casefold() not in stop_words
        }
        answer_terms = {
            token.strip(".,?!:;()[]{}'").casefold()
            for token in answer.split()
            if len(token.strip(".,?!:;()[]{}'")) > 2
        }
        overlap = len(question_terms & answer_terms)
        relevant = bool(overlap)
        evidence_bonus = 2 if any(char.isdigit() for char in answer) else 0
        criteria = CriterionScores(
            relevance=min(20, 4 + overlap * 4) if relevant else 2,
            technical_accuracy=min(20, 5 + word_count // 6) if relevant else 2,
            clarity=min(20, 11 + word_count // 4),
            completeness=min(20, 8 + word_count // 3 + evidence_bonus),
            communication_quality=min(20, 11 + word_count // 5),
        )
        if language == "si":
            return EvaluationResult(
                score=criteria.total,
                criteria=criteria,
                feedback="පිළිතුර පැහැදිලිය; තවත් නිශ්චිත උදාහරණයක් එක් කරන්න.",
                strengths=["ප්‍රශ්නයට සෘජුව පිළිතුරු දී ඇත"],
                improvements=["මැනිය හැකි ප්‍රතිඵලයක් එක් කරන්න"],
                learning_areas=["උදාහරණ සමඟ structured communication"],
            )
        return EvaluationResult(
            score=criteria.total,
            criteria=criteria,
            feedback=(
                "SIMULATED MOCK FEEDBACK: The answer shares terms with the question; "
                "this offline heuristic cannot verify correctness."
                if relevant
                else (
                    "SIMULATED MOCK FEEDBACK: The answer appears unrelated or "
                    "incomplete; connect it directly to the question. This "
                    "heuristic cannot verify correctness."
                )
            ),
            strengths=[
                "Contains question-related terms"
                if relevant
                else "No reliable strength inferred by mock mode"
            ],
            improvements=["Add specific evidence and a direct explanation"],
            learning_areas=["Structuring examples with evidence"],
        )

    def summarize_interview(
        self,
        *,
        mode: str,
        language: str,
        history: list[ConversationTurn],
        configuration: InterviewConfiguration,
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
