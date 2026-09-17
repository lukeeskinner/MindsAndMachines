"""Conservative item identity across sessions; never a frontend decision."""
from backend.app.ingestion.models import stable_id
from backend.app.teaching.targeted_questions import normalized


def fingerprint(question):
    # Choice order, formatting and server ID changes cannot manufacture evidence.
    # Different applications can legitimately share a classification answer.
    cue = normalized(question.prompt)
    if "source recall which ending completes the quoted statement" in cue:
        # Fixed, server-bound source cues identify the fact even if a regenerated
        # pool proposes different distractors. Do not manufacture fresh evidence.
        return stable_id("source-evidence", question.concept_id, cue)
    return stable_id("evidence", question.concept_id, cue,
                     sorted(normalized(c.text) for c in question.choices if c.id != "unsure"))
