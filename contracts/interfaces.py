"""Four structural interfaces; implementations are injected in main.py."""
from typing import Protocol
from contracts.models import (
    Assessment, Candidate, ConceptEstimate, Decision, HistoryEntry,
    LearnerPresentationPreferences, LearnerState, LearnerUpdate, Question, TeachingResult,
)


class Assessor(Protocol):
    async def assess(self, question: Question, answer: str) -> Assessment: ...


class Learner(Protocol):
    def initial_state(self, concept_ids: list[str]) -> LearnerUpdate: ...

    def update(self, state: LearnerState, assessment: Assessment,
               history: list[HistoryEntry]) -> LearnerUpdate: ...


class Policy(Protocol):
    def choose(self, concepts: list[ConceptEstimate], assessment: Assessment,
               candidates: list[Candidate], history: list[HistoryEntry]) -> Decision | None: ...


class Teaching(Protocol):
    async def teach(self, decision: Decision | None, assessment: Assessment,
                    concepts: list[ConceptEstimate],
                    presentation_preferences: LearnerPresentationPreferences) -> TeachingResult: ...
