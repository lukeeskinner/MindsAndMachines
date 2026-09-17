"""Read-only, deterministic coaching priority; no provider or storage access."""
import re
from backend.app.learner.evidence import fingerprint
from contracts.models import CoachContext, FocusPriority


def priority_score(c):
    width = c.interval90.upper - c.interval90.lower
    deficit = max(0, 4 - c.evidence_count) / 4
    return .55 * (1 - c.mean) + .30 * width + .15 * deficit


def rank_focus(concepts, names, questions=(), exposed=()):
    ranked = []
    for c in concepts:
        width = c.interval90.upper - c.interval90.lower
        unseen = sum(q.concept_id == c.concept_id and fingerprint(q) not in exposed for q in questions)
        # A weak, supported estimate and an uncertain estimate are separate
        # signals. Availability is an actionability tie-break, never mastery.
        score = priority_score(c)
        reasons = []
        if c.mean < .5:
            reasons.append("low_mastery")
        if width > .5:
            reasons.append("high_uncertainty")
        if c.evidence_count < 4:
            reasons.append("limited_evidence")
        if not reasons:
            reasons.append("consolidate_learning")
        ranked.append(FocusPriority(concept_id=c.concept_id, concept_name=re.sub(r"^\d+[.)]\s*", "", names[c.concept_id]),
            focus_priority=round(score, 6), mastery_mean=c.mean, interval90=c.interval90,
            evidence_count=c.evidence_count, unseen_questions=unseen, reasons=reasons))
    return sorted(ranked, key=lambda c: (-c.focus_priority, -min(c.unseen_questions, 3), c.concept_id))


def coach_context(runtime, concepts, session, profile):
    names = ({c.concept_id: c.name for c in runtime.course.concepts} if hasattr(runtime, "course")
             else {cid: cid.replace("_", " ").title() for cid in runtime.concept_ids})
    return CoachContext(session_complete=session.question_id is None, session_kind=session.session_kind,
        focus_ranking=rank_focus(concepts, names, runtime.questions.values(), profile.exposed if profile else []))
