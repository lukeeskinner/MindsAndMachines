"""DynamoDB-backed session persistence: the same session/profile seam as
MemoryStore (CONTRACTS.md), so callers never change. Selected in main.py
only when DYNAMODB_TABLE_NAME is set; the in-memory G1 default is
unaffected when unconfigured.
"""
import json
import os
from typing import Any
from uuid import uuid4

from backend.app.storage.memory import Session, LearnerProfile
from dataclasses import asdict
from contracts.models import ChatExchange, HistoryEntry, LearnerState
from backend.app.teaching.remediation import RemediationFocus
from backend.app.teaching.targeted_questions import GeneratedQuestion


def dynamo_configured() -> bool:
    return bool(os.environ.get("DYNAMODB_TABLE_NAME"))


class DynamoStore:
    def __init__(self, table: Any = None) -> None:
        if table is None:
            import boto3  # local import: unconfigured path never needs boto3 installed
            table_name = os.environ["DYNAMODB_TABLE_NAME"]
            region = os.environ.get("AWS_REGION", "us-east-1")
            table = boto3.resource("dynamodb", region_name=region).Table(table_name)
        self._table = table

    def new_session(self, question_id: str, state: LearnerState, user_id: str | None = None,
                    course_id: str | None = None) -> str:
        session_id = str(uuid4())
        self._put(session_id, Session(question_id, state, [], user_id, course_id))
        return session_id

    def load_session(self, session_id: str) -> Session:
        response = self._table.get_item(Key={"session_id": session_id}, ConsistentRead=True)
        item = response.get("Item")
        if item is None:
            raise KeyError(session_id)
        data = json.loads(item["data"])
        return Session(
            question_id=data["question_id"],
            learner_state=LearnerState(**data["learner_state"]),
            history=[HistoryEntry(**entry) for entry in data["history"]],
            user_id=data.get("user_id"),
            course_id=data.get("course_id"),
            profile_id=data.get("profile_id"),
            session_start=LearnerState(**data["session_start"]) if data.get("session_start") else None,
            budget=data.get("budget", 0),
            current_review=data.get("current_review", False),
            session_kind=data.get("session_kind", "diagnostic"),
            focus_concept_id=data.get("focus_concept_id"),
            focus_question_ids=data.get("focus_question_ids", []),
            remediation_focus=RemediationFocus(**data["remediation_focus"]) if data.get("remediation_focus") else None,
            chat_history=[ChatExchange(**entry) for entry in data.get("chat_history", [])],
            generated_questions={key: GeneratedQuestion(**value)
                                 for key, value in data.get("generated_questions", {}).items()},
        )

    def save_session(self, session_id: str, session: Session) -> None:
        self._put(session_id, session)

    def _data(self, session: Session):
        data = {
            "session_kind": session.session_kind,
            "focus_concept_id": session.focus_concept_id,
            "focus_question_ids": session.focus_question_ids,
            "profile_id": session.profile_id,
            "session_start": session.session_start.model_dump() if session.session_start else None,
            "budget": session.budget,
            "current_review": session.current_review,
            "chat_history": [entry.model_dump() for entry in session.chat_history],
            "question_id": session.question_id,
            "learner_state": session.learner_state.model_dump(),
            "history": [entry.model_dump() for entry in session.history],
            "user_id": session.user_id,
            "course_id": session.course_id,
            "remediation_focus": session.remediation_focus.model_dump() if session.remediation_focus else None,
            "generated_questions": {key: value.model_dump() for key, value in session.generated_questions.items()},
        }
        return json.dumps(data)

    def _put(self, session_id: str, session: Session) -> None:
        self._table.put_item(Item={"session_id": session_id, "data": self._data(session)})

    def load_profile(self, profile_id: str):
        item = self._table.get_item(Key={"session_id": "profile:" + profile_id}, ConsistentRead=True).get("Item")
        if item is None:
            raise KeyError(profile_id)
        data = json.loads(item["data"])
        data["state"] = LearnerState(**data["state"])
        return LearnerProfile(**data)

    def save_progress(self, session_id: str, session: Session, profile_id: str, profile):
        data = asdict(profile)
        data["state"] = profile.state.model_dump()
        items = [{"session_id": session_id, "data": self._data(session)},
                 {"session_id": "profile:" + profile_id, "data": json.dumps(data)}]
        self._table.meta.client.transact_write_items(TransactItems=[
            {"Put": {"TableName": self._table.name, "Item": item}} for item in items])
