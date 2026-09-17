"""Local demo state. Restarting the backend discards every session."""
from dataclasses import dataclass, field
from uuid import uuid4
from contracts.models import ChatExchange, HistoryEntry, LearnerState
from backend.app.teaching.remediation import RemediationFocus
from backend.app.teaching.targeted_questions import GeneratedQuestion


@dataclass
class Session:
    question_id: str | None
    learner_state: LearnerState
    history: list[HistoryEntry] = field(default_factory=list)
    user_id: str | None = None
    course_id: str | None = None
    remediation_focus: RemediationFocus | None = None
    generated_questions: dict[str, GeneratedQuestion] = field(default_factory=dict)
    chat_history: list[ChatExchange] = field(default_factory=list)
    profile_id: str | None = None
    session_start: LearnerState | None = None
    budget: int = 0
    current_review: bool = False
    session_kind: str = "diagnostic"
    focus_concept_id: str | None = None
    focus_question_ids: list[str] = field(default_factory=list)


@dataclass
class LearnerProfile:
    state: LearnerState
    course_id: str | None
    user_id: str | None = None
    exposed: list[str] = field(default_factory=list)
    recent: list[str] = field(default_factory=list)
    session_number: int = 0
    active_session_id: str | None = None
    first_question_id: str | None = None
    focus_questions: dict = field(default_factory=dict)
    exposed_stems: list[str] = field(default_factory=list)
    exposed_facts: list[str] = field(default_factory=list)


class MemoryStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}
        self.profiles: dict[str, LearnerProfile] = {}

    def new_session(self, question_id: str, state: LearnerState, user_id: str | None = None,
                    course_id: str | None = None) -> str:
        session_id = str(uuid4())
        self.sessions[session_id] = Session(question_id, state, user_id=user_id, course_id=course_id)
        return session_id

    def load_session(self, session_id: str) -> Session:
        return self.sessions[session_id]

    def save_session(self, session_id: str, session: Session) -> None:
        self.sessions[session_id] = session

    def load_profile(self, profile_id: str) -> LearnerProfile:
        from copy import deepcopy
        return deepcopy(self.profiles[profile_id])

    def save_progress(self, session_id: str, session: Session, profile_id: str, profile: LearnerProfile):
        from copy import deepcopy
        self.sessions[session_id] = deepcopy(session)
        self.profiles[profile_id] = deepcopy(profile)
