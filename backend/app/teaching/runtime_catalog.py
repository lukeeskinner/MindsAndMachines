"""Course-scoped, provider-free runtime adaptation. No session state is stored here."""
from dataclasses import dataclass
from typing import Iterable

from backend.app.ingestion.models import IngestionError, ProcessedCourse, SourceReference, stable_id
from backend.app.ingestion.teaching import DRAFT_NOTICE, PROCESS_TEMPLATES, validate_teaching
from backend.app.storage.courses import adapt_question
from backend.app.teaching.targeted_questions import GeneratedQuestion
from contracts.models import (
    Assessment, Candidate, Choice, ConceptEstimate, Decision,
    LearnerPresentationPreferences, Question, TeachingResult,
)


@dataclass(frozen=True)
class RuntimeAvailability:
    candidates: tuple[Candidate, ...]
    concept_exhausted: bool
    course_exhausted: bool
    # A boundary transition, not a policy decision. The integrator presents this
    # question only after exhausting the current concept, without fabricating an
    # assessment or transferring evidence between concepts.
    next_concept_id: str | None
    next_concept_question_id: str | None


class RuntimeCatalog:
    """A private view of one course, with the small Catalog lookup surface.

    Construction validates stored artifacts; legacy preview-only courses without
    teaching fail explicitly. Each instance owns its mutable runtime copies.
    """

    def __init__(self, course: ProcessedCourse) -> None:
        if not course.course_id or not course.concepts or not course.questions:
            raise IngestionError("Runtime courses need an ID, concepts and questions.")
        self.course = course
        self.concepts = course.concepts
        self.concept_ids = [c.concept_id for c in course.concepts]
        if len(set(self.concept_ids)) != len(self.concept_ids):
            raise IngestionError("Duplicate runtime concept IDs.")
        self.questions: dict[str, Question] = {}
        self.question_provenance = {}
        for source in course.questions:
            if source.question_id in self.questions or source.concept_id not in self.concept_ids:
                raise IngestionError("Duplicate question or unknown runtime concept.")
            ids = [choice.id for choice in source.choices]
            if (not source.question_id or len(set(ids)) != len(ids) or source.answer_key not in ids
                    or source.answer_key in {"unsure", "unscorable"}):
                raise IngestionError("Invalid runtime question choices or answer key.")
            if "unsure" in ids:
                # Do not silently replace a source's unrelated use of the reserved ID.
                raise IngestionError("Source question uses the reserved unsure choice ID.")
            adapted = adapt_question(source)
            adapted.question.choices.append(Choice(id="unsure", text="I'm not sure yet."))
            self.questions[source.question_id] = adapted.question
            self.question_provenance[source.question_id] = adapted.source_refs
        if any(not any(q.concept_id == cid for q in course.questions) for cid in self.concept_ids):
            raise IngestionError("Every runtime concept needs at least one question.")
        first_concept = self.concept_ids[0]
        self.first_question_id = next(q.question_id for q in course.questions if q.concept_id == first_concept)
        self.artifacts = {}
        self.teaching = {}
        self.candidates = []
        seen = set()
        for artifact in course.teaching:
            concept = next((c for c in course.concepts if c.concept_id == artifact.concept_id), None)
            if (concept is None or artifact.teaching_id in self.artifacts
                    or (artifact.concept_id, artifact.kind) in seen):
                raise IngestionError("Duplicate teaching identity/kind or unknown concept.")
            validate_teaching(artifact, concept, course.questions, course.materials)
            seen.add((artifact.concept_id, artifact.kind))
            self.artifacts[artifact.teaching_id] = artifact
            # No paraphrasing: presentation is formatting only. Separate lists
            # prevent accidental mutation across variants or catalog instances.
            self.teaching[artifact.teaching_id] = {
                variant: list(artifact.paragraphs)
                for variant in ("standard", "plain", "concise", "plain_concise")
            }
            for question in course.questions:
                if question.concept_id == artifact.concept_id:
                    self.candidates.append(Candidate(
                        candidate_id=stable_id("candidate", course.course_id, artifact.teaching_id,
                                               question.question_id),
                        concept_id=artifact.concept_id, kind=artifact.kind,
                        content_id=artifact.teaching_id, next_question_id=question.question_id,
                    ))
        if seen != {(cid, kind) for cid in self.concept_ids for kind in PROCESS_TEMPLATES}:
            raise IngestionError("Runtime courses require all three teaching kinds per concept; reprocess legacy artifacts.")
        # Snapshot trusted candidate bindings separately from the policy's copies.
        self._bindings = {c.candidate_id: c.model_dump() for c in self.candidates}
        if len(self._bindings) != len(self.candidates):
            raise IngestionError("Duplicate runtime candidate IDs.")

    def question(self, question_id: str) -> Question:
        return self.questions[question_id].model_copy(deep=True)

    def apply_session_questions(self, generated_questions: dict[str, GeneratedQuestion]) -> None:
        """Replace fresh bank slots on this request's catalog, never the course artifact."""
        for key, record in generated_questions.items():
            question = record.question
            original = self.questions.get(record.replaces_question_id)
            if (record.course_id != self.course.course_id or key != question.question_id
                    or original is None or original.concept_id != question.concept_id
                    or key in self.questions):
                raise ValueError("Foreign session question overlay")
            self.questions = {
                key if qid == record.replaces_question_id else qid:
                question.model_copy(deep=True) if qid == record.replaces_question_id else item
                for qid, item in self.questions.items()
            }
            self.question_provenance[key] = (SourceReference(record.source_chunk_id, record.source_quote),)
            for candidate in self.candidates:
                if candidate.next_question_id == record.replaces_question_id:
                    candidate.next_question_id = key
        self._bindings = {c.candidate_id: c.model_dump() for c in self.candidates}

    def eligible_candidates(self, *, current_question_id: str,
                            consumed_question_ids: Iterable[str] = (),
                            consumed_candidate_ids: Iterable[str] = ()) -> RuntimeAvailability:
        """Exclude every consumed question, even an unscored/unsure submission.

        Stay within the current concept until its question pool is empty, then
        propose the first remaining concept/question in artifact order. Completion
        is based on question exhaustion, never just a null policy decision.
        """
        current = self.questions[current_question_id]
        consumed = set(consumed_question_ids) | {current_question_id}
        used_candidates = set(consumed_candidate_ids)
        if not consumed <= self.questions.keys() or not used_candidates <= self._bindings.keys():
            raise ValueError("Consumed IDs must belong to this course catalog.")
        remaining = [q for q in self.questions.values() if q.question_id not in consumed]
        local = [q for q in remaining if q.concept_id == current.concept_id]
        next_question = next((q for cid in self.concept_ids for q in remaining if q.concept_id == cid), None)
        eligible = tuple(Candidate(**binding) for binding in self._bindings.values()
                         if binding["concept_id"] == current.concept_id
                         and binding["next_question_id"] not in consumed
                         and binding["candidate_id"] not in used_candidates)
        return RuntimeAvailability(
            candidates=eligible, concept_exhausted=not local, course_exhausted=not remaining,
            next_concept_id=next_question.concept_id if not local and next_question else None,
            next_concept_question_id=next_question.question_id if not local and next_question else None,
        )

    def render(self, decision: Decision, assessment: Assessment, concepts: list[ConceptEstimate],
               preferences: LearnerPresentationPreferences) -> TeachingResult:
        """Provider-free deterministic rendering; Tutor may personalize separately."""
        binding = self._bindings.get(decision.candidate_id)
        if binding != decision.model_dump(exclude={"reason"}):
            raise ValueError("Decision does not match the trusted course candidate.")
        if sum(c.concept_id == decision.concept_id for c in concepts) != 1:
            raise ValueError("Expected exactly one estimate for the selected course concept.")
        artifact = self.artifacts[decision.content_id]
        if (artifact.teaching_id != decision.content_id or artifact.kind != decision.kind
                or artifact.concept_id != decision.concept_id):
            raise ValueError("Teaching artifact does not match the trusted course candidate.")
        concept = next(c for c in self.concepts if c.concept_id == decision.concept_id)
        validate_teaching(artifact, concept, self.course.questions, self.course.materials)
        # Render the immutable artifact, never mutable caller-supplied prose,
        # feedback, IDs, source quotes or private question records.
        text = ("\n".join(f"{i}. {p}" for i, p in enumerate(artifact.paragraphs, 1))
                if preferences.step_by_step else "\n\n".join(artifact.paragraphs))
        # The existing shared enum has no draft value. Keep review status private
        # and identify unreviewed teaching in prose without claiming human review.
        if artifact.requires_review:
            text = DRAFT_NOTICE + "\n\n" + text
        return TeachingResult(
            text=text, next_question_id=decision.next_question_id,
            fallback=assessment.outcome == "unclear",
            teaching_source="authored_fallback" if assessment.outcome == "unclear" else "authored",
        )


def build_runtime_catalog(processed_course: ProcessedCourse) -> RuntimeCatalog:
    return RuntimeCatalog(processed_course)
