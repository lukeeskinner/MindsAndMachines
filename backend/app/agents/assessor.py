from contracts.models import Assessment, Question


class FakeAssessor:
    """Deterministic answer-key lookup for the authored demo questions."""

    async def assess(self, question: Question, answer: str) -> Assessment:
        if answer == "unsure":
            return Assessment(outcome="unclear", concept_id=question.concept_id,
                              score=None, misconception_id=None,
                              feedback="No evidence applied. Let's look at an example together.")
        correct = answer == question.answer_key
        return Assessment(
            outcome="correct" if correct else "incorrect",
            concept_id=question.concept_id,
            score=1 if correct else 0,
            misconception_id=None if correct else "admissible_means_consistent",
            feedback=("That's right: admissibility does not guarantee consistency."
                      if correct else
                      "The distinction to revisit: an admissible heuristic need not be consistent."),
        )
