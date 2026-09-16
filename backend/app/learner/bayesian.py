"""Independent Beta(1, 1) priors updated by eligible binary observations."""
import math

from contracts.models import (
    Assessment, ConceptEstimate, HistoryEntry, LearnerState, LearnerUpdate, SkillState,
)


def _beta_cdf(x: float, alpha: int, beta: int) -> float:
    """Integer-parameter Beta CDF via the binomial tail, for x in [0, 1]."""
    if x == 0.0:
        return 0.0
    if x == 1.0:
        return 1.0
    n = alpha + beta - 1
    log_x, log_complement = math.log(x), math.log1p(-x)
    # Log terms avoid overflowing large binomial coefficients before scaling.
    total = math.fsum(
        math.exp(math.log(math.comb(n, j)) + j * log_x + (n - j) * log_complement)
        for j in range(alpha, n + 1)
    )
    return min(1.0, total)  # Summation roundoff can put the CDF just above one.


def _beta_quantile(probability: float, alpha: int, beta: int) -> float:
    """Invert the CDF with a bounded search; callers supply validated parameters."""
    lower, upper = 0.0, 1.0
    # Fifty bisections resolve x to about 1e-15 before public rounding.
    for _ in range(50):
        midpoint = (lower + upper) / 2
        if _beta_cdf(midpoint, alpha, beta) < probability:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2


def _result(state: LearnerState, applied: bool) -> LearnerUpdate:
    concepts = [
        ConceptEstimate(
            concept_id=concept_id,
            mean=skill.alpha / (skill.alpha + skill.beta),
            interval90={
                "lower": round(_beta_quantile(0.05, skill.alpha, skill.beta), 4),
                "upper": round(_beta_quantile(0.95, skill.alpha, skill.beta), 4),
            },
            evidence_count=skill.evidence_count,
        )
        for concept_id, skill in state.skills.items()
    ]
    return LearnerUpdate(state=state, concepts=concepts, evidence_applied=applied)


class BayesianLearner:
    """Consume evidence already deemed eligible upstream.

    The protocol lacks current question identity and assistance metadata, so
    freshness, unaided status and duplicate checks belong upstream. History is
    accepted for protocol compatibility and does not control these updates.
    """

    def initial_state(self, concept_ids: list[str]) -> LearnerUpdate:
        if len(set(concept_ids)) != len(concept_ids):
            raise ValueError("Duplicate initial concept IDs are not allowed")
        state = LearnerState(skills={
            concept_id: SkillState(alpha=1, beta=1, evidence_count=0)
            for concept_id in concept_ids
        })
        return _result(state, False)

    def update(self, state: LearnerState, assessment: Assessment,
               history: list[HistoryEntry]) -> LearnerUpdate:
        for concept_id, skill in state.skills.items():
            if skill.alpha < 1 or skill.beta < 1 or skill.evidence_count < 0:
                raise ValueError(
                    f"Invalid state for concept {concept_id!r}: alpha and beta must "
                    "be >= 1 and evidence_count must be >= 0"
                )
            if skill.evidence_count != skill.alpha + skill.beta - 2:
                raise ValueError(
                    f"Invalid state for concept {concept_id!r}: "
                    "evidence_count must equal alpha + beta - 2"
                )
        if assessment.concept_id not in state.skills:
            raise ValueError(f"Unknown concept {assessment.concept_id!r} in assessment")
        expected_score = {"correct": 1, "incorrect": 0, "unclear": None}[assessment.outcome]
        if assessment.score != expected_score:
            raise ValueError(
                f"Contradictory assessment: outcome {assessment.outcome!r} "
                f"requires score {expected_score!r}, got {assessment.score!r}"
            )

        updated = state.model_copy(deep=True)
        if assessment.score is not None:
            skill = updated.skills[assessment.concept_id]
            skill.alpha += assessment.score
            skill.beta += 1 - assessment.score
            skill.evidence_count += 1
        return _result(updated, assessment.score is not None)
