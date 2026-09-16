"""Local demo state. Restarting the backend discards every session."""
from dataclasses import dataclass, field
from uuid import uuid4
from contracts.models import HistoryEntry, LearnerState


@dataclass
class Session:
    question_id: str | None
    learner_state: LearnerState
    history: list[HistoryEntry] = field(default_factory=list)


class MemoryStore:
    def __init__(self) -> None:
        self.sessions: dict[str, Session] = {}

    def new_session(self, question_id: str, state: LearnerState) -> str:
        session_id = str(uuid4())
        self.sessions[session_id] = Session(question_id, state)
        return session_id

    def load_session(self, session_id: str) -> Session:
        return self.sessions[session_id]

    def save_session(self, session_id: str, session: Session) -> None:
        self.sessions[session_id] = session
