"""Canned states only. There is no Bayesian calculation or policy math here."""
from contracts.models import (
    Assessment, ConceptEstimate, HistoryEntry, LearnerState, LearnerUpdate, SkillState,
)

# Fixed approved G1 values, keyed by the canned evidence count.
VALUES = {
    0: {"alpha": 1, "beta": 1, "mean": 0.5, "lower": 0.05, "upper": 0.95},
    1: {"alpha": 1, "beta": 2, "mean": 0.3333333333333333, "lower": 0.0253, "upper": 0.7764},
    2: {"alpha": 2, "beta": 2, "mean": 0.5, "lower": 0.1354, "upper": 0.8646},
}


class FakeLearner:
    def _result(self, state: LearnerState, applied: bool) -> LearnerUpdate:
        concepts = []
        for concept_id, skill in state.skills.items():
            value = VALUES[skill.evidence_count]
            concepts.append(ConceptEstimate(
                concept_id=concept_id, mean=value["mean"], alpha=skill.alpha, beta=skill.beta,
                interval90={"lower": value["lower"], "upper": value["upper"]},
                evidence_count=skill.evidence_count,
            ))
        return LearnerUpdate(state=state, concepts=concepts, evidence_applied=applied)

    def initial_state(self, concept_ids: list[str]) -> LearnerUpdate:
        state = LearnerState(skills={
            key: SkillState(alpha=1, beta=1, evidence_count=0) for key in concept_ids
        })
        return self._result(state, False)

    def update(self, state: LearnerState, assessment: Assessment,
               history: list[HistoryEntry]) -> LearnerUpdate:
        updated = state.model_copy(deep=True)
        count = updated.skills[assessment.concept_id].evidence_count
        next_count = None
        if not history and assessment.score == 0:
            next_count = 1
        elif len(history) == 1 and count == 1 and assessment.score == 1:
            next_count = 2
        if next_count is not None:
            value = VALUES[next_count]
            updated.skills[assessment.concept_id] = SkillState(
                alpha=value["alpha"], beta=value["beta"], evidence_count=next_count,
            )
        return self._result(updated, next_count is not None)
