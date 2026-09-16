"""App-owned private course artifacts and a preview-only question boundary.

These records do not supply Tutor content or policy candidates. Never serialize
the registry or ProcessedCourse as an API response; use public_metadata().
"""
from dataclasses import dataclass

from backend.app.ingestion.models import ProcessedCourse, Question as IngestionQuestion, SourceReference
from contracts.models import Choice, PublicCourse, PublicCourseConcept, Question


@dataclass(frozen=True)
class AdaptedQuestion:
    question: Question
    source_refs: tuple[SourceReference, ...]


def adapt_question(source: IngestionQuestion) -> AdaptedQuestion:
    """Retain provenance separately from the runtime/public question contracts.

    Choices are unchanged. Generated-course abstention still needs an explicit
    unsure choice or a later route contract before learning can be activated.
    """
    return AdaptedQuestion(
        question=Question(
            question_id=source.question_id, concept_id=source.concept_id,
            prompt=source.prompt,
            choices=[Choice(id=choice.id, text=choice.text) for choice in source.choices],
            answer_key=source.answer_key, rubric=source.explanation,
        ),
        source_refs=source.source_refs,
    )


@dataclass(frozen=True)
class CourseCatalog:
    """Private view of one immutable artifact, independent of the demo Catalog."""

    course: ProcessedCourse

    @property
    def concept_ids(self) -> list[str]:
        return [concept.concept_id for concept in self.course.concepts]

    @property
    def first_question_id(self) -> str:
        return self.course.questions[0].question_id

    def question(self, question_id: str) -> AdaptedQuestion:
        for question in self.course.questions:
            if question.question_id == question_id:
                return adapt_question(question)
        raise KeyError(question_id)

    def public_metadata(self) -> PublicCourse:
        return PublicCourse(
            course_id=self.course.course_id, title=self.course.title,
            concepts=[PublicCourseConcept(concept_id=c.concept_id, display_name=c.name)
                      for c in self.course.concepts],
            source_filenames=[material.filename for material in self.course.materials],
            question_count=len(self.course.questions),
        )


class MemoryCourseRegistry:
    """Process-local ownership; registration never replaces a stored artifact.

    Ingestion IDs identify source inputs, so regenerated content can share an ID.
    Equal registration is harmless; different content under that ID is rejected
    to keep existing sessions bound to their original artifact.
    """

    def __init__(self) -> None:
        self._courses: dict[str, ProcessedCourse] = {}

    def register(self, course: ProcessedCourse) -> str:
        if not course.course_id or not course.concepts or not course.questions:
            raise ValueError("A processed course needs an ID, concepts and questions.")
        existing = self._courses.get(course.course_id)
        if existing is not None and existing != course:
            raise ValueError("Course ID already belongs to a different artifact.")
        self._courses[course.course_id] = course
        return course.course_id

    def get(self, course_id: str) -> ProcessedCourse:
        return self._courses[course_id]

    def catalog(self, course_id: str) -> CourseCatalog:
        return CourseCatalog(self.get(course_id))
