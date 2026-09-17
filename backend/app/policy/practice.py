"""Deterministic evidence collection, separate from intervention selection."""
from collections import Counter
from dataclasses import dataclass, field
from backend.app.teaching.runtime_catalog import RuntimeAvailability


def has_pools(runtime):
    return runtime.course.metadata.schema_version == "2" or all(sum(q.concept_id == cid for q in runtime.questions.values()) >= 3
               for cid in runtime.concept_ids)


def session_budget(runtime):
    if not has_pools(runtime):
        return len(runtime.questions)
    return min(len(runtime.questions), max(2 * len(runtime.concept_ids), min(12, 3 * len(runtime.concept_ids) - 2)))


@dataclass
class PracticeSelection:
    recent: list[str] = field(default_factory=list)
    session_number: int = 0
    budget: int = 10
    avoid_first: str | None = None

    def pick(self, runtime, concepts, history, current=None, assessment=None):
        consumed = {h.question_id for h in history}
        if current:
            consumed.add(current.question_id)
        remaining = [q for q in runtime.questions.values() if q.question_id not in consumed]
        if not consumed and len(remaining) > 1 and self.avoid_first:
            remaining = [q for q in remaining if q.question_id != self.avoid_first]
        if len(consumed) >= self.budget or not remaining:
            return None
        counts = Counter(runtime.questions[qid].concept_id for qid in consumed if qid in runtime.questions)
        estimates = {c.concept_id: c for c in concepts}
        previous_concept = runtime.questions[history[-1].question_id].concept_id if history else None
        retry = current and assessment and assessment.outcome == 'incorrect' and previous_concept != current.concept_id
        fresh = [q for q in remaining if q.question_id not in self.recent]
        eligible = fresh or remaining
        if retry:
            local = [q for q in eligible if q.concept_id == current.concept_id]
            if local:
                eligible = local
        positions = {cid: (i - self.session_number) % len(runtime.concept_ids)
                     for i, cid in enumerate(runtime.concept_ids)}
        def key(q):
            c = estimates[q.concept_id]
            tier = min(counts[q.concept_id], 2)
            score = (1 - c.mean) + (c.interval90.upper - c.interval90.lower)
            recency = self.recent.index(q.question_id) if q.question_id in self.recent else -1
            return (tier, -score, recency, positions[q.concept_id], q.question_id)
        return min(eligible, key=key)

    def availability(self, runtime, concepts, history, current, assessment):
        chosen = self.pick(runtime, concepts, history, current, assessment)
        from contracts.models import Candidate
        from backend.app.ingestion.models import stable_id
        candidates = []
        if chosen:
            # Teaching still addresses the assessed concept; question selection
            # may now collect evidence from a different concept for coverage.
            for artifact in runtime.artifacts.values():
                if artifact.concept_id == current.concept_id:
                    candidate = Candidate(
                        candidate_id=stable_id("practice", current.question_id, chosen.question_id, artifact.teaching_id),
                        concept_id=current.concept_id, kind=artifact.kind,
                        content_id=artifact.teaching_id, next_question_id=chosen.question_id)
                    runtime._bindings[candidate.candidate_id] = candidate.model_dump()
                    candidates.append(candidate)
        return RuntimeAvailability(tuple(candidates), chosen is None, chosen is None, None, None)
