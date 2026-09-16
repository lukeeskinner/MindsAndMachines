from contracts.models import Assessment, Candidate, ConceptEstimate, Decision, HistoryEntry


class FakePolicy:
    """One fixed first intervention, then completion. No ranking or scoring math."""

    def choose(self, concepts: list[ConceptEstimate], assessment: Assessment,
               candidates: list[Candidate], history: list[HistoryEntry]) -> Decision | None:
        if history:
            return None
        candidate = candidates[0]
        return Decision(**candidate.model_dump(), reason=(
            "A worked example contrasts the two conditions before a fresh question. "
            "This selection is scripted for the deterministic baseline."
        ))
