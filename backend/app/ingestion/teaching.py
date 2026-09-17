"""Conservative source and disclosure checks, not a semantic verifier."""
import re

from .models import Concept, IngestionError, Question, SourceMaterial, TeachingArtifact, normalized


DRAFT_NOTICE = "Draft course guidance."


# General reading processes introduce no subject-matter facts. The selected
# concept and private citations supply context, without copying its answer.
PROCESS_TEMPLATES = {
    "diagnostic_probe": (
        "What detail in the cited material would help you respond to the displayed task?",
    ),
    "socratic_hint": (
        "Look for the condition or relationship described in the cited passage. "
        "Which part of the displayed task depends on it?",
    ),
    "worked_example": (
        "Here is a reading process: first identify what the displayed task asks you to find.",
        "Locate the relevant passage and separate its stated condition from its consequence.",
        "Compare that relationship with each proposed response, ruling out unsupported claims.",
    ),
}


def contains_phrase(text: str, phrase: str) -> bool:
    """Case/whitespace-insensitive exact phrase, with word boundaries.

    Avoid matching a one-letter answer inside an unrelated word. This cannot
    detect paraphrases, implication, or all punctuation-based evasions.
    """
    phrase = normalized(phrase).casefold()
    return bool(phrase and re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)",
                                    normalized(text).casefold()))


def validate_teaching(artifact: TeachingArtifact, concept: Concept,
                      questions: tuple[Question, ...], materials: tuple[SourceMaterial, ...]) -> None:
    """Every candidate binds this item only to questions of its own concept.

    Accept exact cited passages or kind-specific process templates. Requiring
    extractive subject facts deliberately rejects new examples/paraphrases that
    citations alone cannot substantiate. Independent examples already in the
    source are possible; otherwise the process template is the safe alternative.
    """
    if (artifact.kind not in PROCESS_TEMPLATES or artifact.concept_id != concept.concept_id
            or not artifact.teaching_id or type(artifact.requires_review) is not bool):
        raise IngestionError("Invalid teaching identity, concept or kind.")
    paragraphs = artifact.paragraphs
    if (not isinstance(paragraphs, tuple) or not 1 <= len(paragraphs) <= 4
            or any(not isinstance(p, str) or not p.strip() or len(p) > 800 for p in paragraphs)
            or (artifact.kind == "worked_example" and len(paragraphs) < 2)):
        raise IngestionError("Invalid teaching paragraphs.")
    text = " ".join(paragraphs)
    if artifact.kind != "worked_example" and len(text) > 360:
        raise IngestionError("Probe or hint exceeds the teaching budget.")
    chunks = {c.chunk_id: c for m in materials for c in m.chunks if c.status == "extracted"}
    concept_chunks = {ref.chunk_id for ref in concept.source_refs}
    refs = artifact.source_refs
    if (not 1 <= len(refs) <= 4 or len({r.chunk_id for r in refs}) != len(refs)
            or any(r.chunk_id not in chunks or r.chunk_id not in concept_chunks
                   or not r.quote.strip() or r.quote not in chunks[r.chunk_id].normalized_text for r in refs)):
        raise IngestionError("Teaching lacks valid concept source references.")
    protected = [q.explanation for q in questions]
    protected += [choice.text for q in questions for choice in q.choices if choice.id == q.answer_key]
    display_text = DRAFT_NOTICE + " " + text if artifact.requires_review else text
    if any(contains_phrase(display_text, value) for value in protected):
        raise IngestionError("Teaching contains a private rubric or correct-choice text.")
    # These guards apply to authored source excerpts too: uploaded instructions
    # are data, not authority to control the tutor or disclose private records.
    forbidden = (
        r"\b(?:answer[ -]?key|rubrics?|system (?:prompt|message|instruction)|developer message)\b",
        r"\b(?:ignore|override)\b.{0,60}\b(?:instructions?|rules?)\b",
        r"\b(?:correct|right|expected) (?:answer|option|choice)\b",
        r"\b(?:answer|solution)\s*(?:is\b|=|:)",
        r"\b(?:choose|select|pick|mark)\s+(?:option\s+|choice\s+)?[a-d]\b",
        r"\b(?:mastery|posterior|evidence count|next_question_id|candidate_id)\b",
        r"\b(?:change|replace|skip|switch)\b.{0,30}\b(?:question|activity|concept)\b",
    )
    if any(re.search(rule, text, re.IGNORECASE) for rule in forbidden):
        raise IngestionError("Teaching contains control instructions or answer disclosure.")
    internal_ids = [artifact.teaching_id, artifact.concept_id]
    internal_ids += [q.question_id for q in questions] + [r.chunk_id for r in refs]
    if any(identifier in text for identifier in internal_ids):
        raise IngestionError("Teaching exposes internal identifiers.")
    for paragraph in paragraphs:
        if (paragraph not in PROCESS_TEMPLATES[artifact.kind]
                and not any(paragraph in ref.quote for ref in refs)):
            raise IngestionError("Teaching prose is not supported by cited text or a process template.")
