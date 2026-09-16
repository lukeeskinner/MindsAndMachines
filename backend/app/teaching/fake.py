from contracts.models import (
    Assessment, ConceptEstimate, Decision, LearnerPresentationPreferences, TeachingResult,
)
from backend.app.teaching.catalog import Catalog


class FakeTutor:
    """Only this module sees presentation preferences; all wording is authored."""

    def __init__(self, catalog: Catalog) -> None:
        self.catalog = catalog

    async def teach(self, decision: Decision | None, assessment: Assessment,
                    concepts: list[ConceptEstimate],
                    presentation_preferences: LearnerPresentationPreferences) -> TeachingResult:
        if decision is None:
            return TeachingResult(
                text="This two-question demo is complete. Start a new session to replay it.",
                next_question_id=None, fallback=assessment.outcome == "unclear",
                teaching_source="authored_fallback" if assessment.outcome == "unclear" else "authored",
            )
        prefs = presentation_preferences
        variant = ("plain_concise" if prefs.plain_language and prefs.concise else
                   "plain" if prefs.plain_language else
                   "concise" if prefs.concise else "standard")
        paragraphs = self.catalog.teaching[decision.content_id][variant]
        text = ("\n".join(f"{index}. {part}" for index, part in enumerate(paragraphs, 1))
                if prefs.step_by_step else "\n\n".join(paragraphs))
        fallback = assessment.outcome == "unclear"
        if fallback:
            text = "Let's try another example.\n\n" + text
        return TeachingResult(text=text, next_question_id=decision.next_question_id, fallback=fallback,
                              teaching_source="authored_fallback" if fallback else "authored")
