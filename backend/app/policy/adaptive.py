"""Deterministic, hand-designed selection priorities over supplied activities."""
import math

from contracts.models import Assessment, Candidate, ConceptEstimate, Decision, HistoryEntry


_NAMES = {
    "diagnostic_probe": "Diagnostic probe",
    "worked_example": "Worked example",
    "socratic_hint": "Socratic hint",
}


def _validate_estimate(concept: ConceptEstimate) -> None:
    if not math.isfinite(concept.mean) or not 0 <= concept.mean <= 1:
        raise ValueError(f"Invalid mean for concept {concept.concept_id!r}: must be finite and in [0, 1]")
    lower, upper = concept.interval90.lower, concept.interval90.upper
    if not (math.isfinite(lower) and math.isfinite(upper) and 0 <= lower <= upper <= 1):
        raise ValueError(
            f"Invalid interval for concept {concept.concept_id!r}: "
            "endpoints must be finite and satisfy 0 <= lower <= upper <= 1"
        )
    if concept.evidence_count < 0:
        raise ValueError(f"Invalid evidence_count for concept {concept.concept_id!r}: must be >= 0")


def _priority(kind: str, m: float, u: float, d: int) -> float:
    """A selection heuristic, not a learning probability or treatment effect."""
    if kind == "diagnostic_probe":
        return 0.65 * u + 0.35 * m
    if kind == "worked_example":
        return 0.65 * m + 0.35 * d
    if kind == "socratic_hint":
        return 0.50 * m + 0.30 * d + 0.20 * u
    raise ValueError(f"Unsupported candidate kind: {kind!r}")


class AdaptivePolicy:
    """Rank unused candidates for the assessed concept without changing inputs.

    Prior candidate IDs support repetition filtering only. The protocol does
    not expose the current question ID, so this does not prove question freshness.
    """

    def choose(self, concepts: list[ConceptEstimate], assessment: Assessment,
               candidates: list[Candidate], history: list[HistoryEntry]) -> Decision | None:
        targets = [c for c in concepts if c.concept_id == assessment.concept_id]
        if len(targets) != 1:
            raise ValueError(
                f"Expected exactly one estimate for concept {assessment.concept_id!r}; "
                f"found {len(targets)}"
            )
        target = targets[0]
        _validate_estimate(target)
        candidate_ids = [candidate.candidate_id for candidate in candidates]
        if len(set(candidate_ids)) != len(candidate_ids):
            raise ValueError("Duplicate candidate IDs are not allowed")

        used_ids = {entry.candidate_id for entry in history if entry.candidate_id is not None}
        eligible = [candidate for candidate in candidates
                    if candidate.concept_id == assessment.concept_id
                    and candidate.candidate_id not in used_ids]
        if not eligible:
            return None

        m = 1 - target.mean
        u = target.interval90.upper - target.interval90.lower
        d = int(
            assessment.concept_id == target.concept_id
            and assessment.outcome == "incorrect"
            and assessment.score == 0
            and assessment.misconception_id is not None
            and bool(assessment.misconception_id.strip())
        )
        scored = [(candidate, _priority(candidate.kind, m, u, d)) for candidate in eligible]
        candidate, score = min(scored, key=lambda item: (-item[1], item[0].candidate_id))
        return Decision(**candidate.model_dump(), reason=(
            f"{_NAMES[candidate.kind]} selected — selection priority {score:.4f} "
            f"from mastery gap {m:.4f}, uncertainty {u:.4f}, "
            f"and misconception signal {d}."
        ))
