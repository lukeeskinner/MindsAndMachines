"""The approved G1 records. Presentation preferences belong only to Teaching."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Choice(Record):
    id: str
    text: str


class PublicQuestion(Record):
    question_id: str
    concept_id: str
    prompt: str
    choices: list[Choice]
    review: bool = False


class Question(PublicQuestion):
    answer_key: str
    rubric: str

    def public(self) -> PublicQuestion:
        return PublicQuestion(**self.model_dump(exclude={"answer_key", "rubric"}))


class PublicCourseConcept(Record):
    concept_id: str
    display_name: str


class PublicCourse(Record):
    course_id: str
    title: str
    concepts: list[PublicCourseConcept]
    source_filenames: list[str]
    question_count: int


class Assessment(Record):
    outcome: Literal["correct", "incorrect", "unclear"]
    concept_id: str
    score: Literal[0, 1] | None
    misconception_id: str | None
    feedback: str


class Interval(Record):
    lower: float
    upper: float


class ConceptEstimate(Record):
    alpha: int | None = Field(default=None, ge=1)
    beta: int | None = Field(default=None, ge=1)
    concept_id: str
    mean: float
    interval90: Interval
    evidence_count: int


class FocusPriority(Record):
    concept_id: str
    concept_name: str
    focus_priority: float
    mastery_mean: float
    interval90: Interval
    evidence_count: int
    unseen_questions: int
    reasons: list[str]


class CoachContext(Record):
    session_complete: bool
    session_kind: Literal["diagnostic", "focus"] = "diagnostic"
    focus_ranking: list[FocusPriority]


class FocusRequest(Record):
    session_id: str
    concept_id: str


class SkillState(Record):
    alpha: int
    beta: int
    evidence_count: int


class LearnerState(Record):
    skills: dict[str, SkillState]


class LearnerUpdate(Record):
    state: LearnerState
    concepts: list[ConceptEstimate]
    evidence_applied: bool


class LearnerPresentationPreferences(Record):
    plain_language: StrictBool = False
    step_by_step: StrictBool = False
    concise: StrictBool = False


class Candidate(Record):
    candidate_id: str
    concept_id: str
    kind: Literal["diagnostic_probe", "worked_example", "socratic_hint"]
    content_id: str
    next_question_id: str | None


class Decision(Candidate):
    reason: str


TeachingSource = Literal["authored", "bedrock", "authored_fallback"]


class TeachingResult(Record):
    text: str
    next_question_id: str | None
    fallback: bool
    teaching_source: TeachingSource = "authored"


class HistoryEntry(Record):
    question_id: str
    evidence_applied: bool
    candidate_id: str | None
    review: bool = False


class PublicAssessment(Record):
    outcome: Literal["correct", "incorrect", "unclear"]
    misconception_id: str | None
    feedback: str


class PublicDecision(Record):
    candidate_id: str
    concept_id: str
    kind: Literal["diagnostic_probe", "worked_example", "socratic_hint"]
    reason: str


class TutorResponse(Record):
    text: str
    fallback: bool
    teaching_source: TeachingSource = "authored"


class TurnRequest(Record):
    session_id: str
    question_id: str
    answer: str = Field(min_length=1, max_length=4000)
    presentation_preferences: LearnerPresentationPreferences = Field(
        default_factory=LearnerPresentationPreferences
    )


class SessionRequest(Record):
    previous_session_id: str | None = None
    reset_learner: bool = False
    course_id: str | None = Field(default=None, min_length=1)


class ChatRequest(Record):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    presentation_preferences: LearnerPresentationPreferences = Field(
        default_factory=LearnerPresentationPreferences
    )


class ChatExchange(Record):
    message: str
    text: str
    teaching_source: Literal["authored", "bedrock"]


class ChatResponse(ChatExchange):
    session_id: str
    analytics: CoachContext | None = None
    practice_concept_id: str | None = None


class Flashcard(Record):
    card_id: str
    concept_id: str
    front: str
    back: str
    source: str


class PracticeCounts(Record):
    submitted_answers: int = 0
    unique_questions_seen: int = 0
    accepted_observations: int = 0
    review_attempts: int = 0
    focus_observations: int = 0
    lifetime_evidence: int = 0


class SessionResponse(Record):
    analytics: CoachContext | None = None
    session_kind: Literal["diagnostic", "focus"] = "diagnostic"
    focus_concept_id: str | None = None
    practice_notice: str = ""
    session_id: str
    course_id: str | None = None
    question: PublicQuestion
    concepts: list[ConceptEstimate]
    question_count: int = Field(default=0, ge=0)
    counts: PracticeCounts = Field(default_factory=PracticeCounts)
    session_start: list[ConceptEstimate] = Field(default_factory=list)
    flashcards: list[Flashcard] = Field(default_factory=list)


class TurnResponse(Record):
    analytics: CoachContext | None = None
    session_id: str
    assessment: PublicAssessment
    concepts: list[ConceptEstimate]
    decision: PublicDecision | None
    tutor: TutorResponse
    next_question: PublicQuestion | None
    # Describe the returned teaching, not the assessor or configured provider.
    mode: Literal["dummy", "live"] = "dummy"
    provider: Literal["fake", "bedrock"] = "fake"
    trace: list[str]
    counts: PracticeCounts = Field(default_factory=PracticeCounts)
    session_start: list[ConceptEstimate] = Field(default_factory=list)
    flashcards: list[Flashcard] = Field(default_factory=list)
