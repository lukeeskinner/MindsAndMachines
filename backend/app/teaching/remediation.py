"""Private, derived review focus; learner estimates remain the sole mastery state."""
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.app.teaching.targeted_questions import GeneratedQuestion

from contracts.models import Assessment, ConceptEstimate, Decision, Flashcard, Record


class RemediationFocus(Record):
    course_id: str | None
    concept_id: str
    misconception_id: str | None
    triggering_question_id: str
    outcome: str = "incorrect"
    evidence_source: str = "answer_key"


def derive_focus(previous: RemediationFocus | None, assessment: Assessment,
                 evidence_applied: bool, question_id: str,
                 course_id: str | None) -> RemediationFocus | None:
    if previous is not None and previous.course_id != course_id:
        previous = None
    if not evidence_applied:
        return previous
    if assessment.outcome == "incorrect" and assessment.score == 0:
        return RemediationFocus(course_id=course_id, concept_id=assessment.concept_id,
                                misconception_id=assessment.misconception_id,
                                triggering_question_id=question_id)
    if previous is not None and previous.concept_id == assessment.concept_id:
        return None
    return previous


def should_generate(focus: RemediationFocus | None, assessment: Assessment,
                    evidence_applied: bool, decision: Decision | None) -> bool:
    return bool(focus and evidence_applied and assessment.outcome == "incorrect"
                and assessment.score == 0 and decision and decision.next_question_id
                and decision.concept_id == assessment.concept_id == focus.concept_id)


# Reviewed content mapping, not a diagnosis inferred from a card interaction.
DEMO_CARD_MISCONCEPTIONS = {"demo-card-6": "admissible_means_consistent"}


def rank_flashcards(cards: list[Flashcard], estimates: list[ConceptEstimate],
                    focus: RemediationFocus | None, course_id: str | None,
                    misconceptions: dict[str, str] | None = None) -> list[Flashcard]:
    """Stable lexicographic order: focus, matching card, trusted focus score, original order.

    Uses the coach policy score. An absent concept/card
    leaves authored tie order intact. Callers supply only the active course deck.
    """
    from backend.app.policy.focus import priority_score
    priorities = {estimate.concept_id: priority_score(estimate) for estimate in estimates}
    focus = focus if focus and focus.course_id == course_id else None
    tags = misconceptions if misconceptions is not None else (
        DEMO_CARD_MISCONCEPTIONS if course_id is None else {})

    def key(card: Flashcard):
        focused = bool(focus and card.concept_id == focus.concept_id)
        specific = bool(focused and focus.misconception_id
                        and tags.get(card.card_id) == focus.misconception_id)
        return (not focused, not specific, -priorities.get(card.concept_id, 0.0))

    return sorted(cards, key=key)


@dataclass
class RemediationTurn:
    """API-owned per-request scratch result, committed only with a successful turn."""
    course_id: str | None
    focus: RemediationFocus | None = None
    generated: "GeneratedQuestion | None" = None
