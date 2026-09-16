"""DynamoDB-backed session persistence: the same three-method seam as
MemoryStore (CONTRACTS.md), so callers never change. Selected in main.py
only when DYNAMODB_TABLE_NAME is set; the in-memory G1 default is
unaffected when unconfigured.
"""
import json
import os
from typing import Any
from uuid import uuid4

from backend.app.storage.memory import Session
from contracts.models import HistoryEntry, LearnerState


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
        response = self._table.get_item(Key={"session_id": session_id})
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
        )

    def save_session(self, session_id: str, session: Session) -> None:
        self._put(session_id, session)

    def _put(self, session_id: str, session: Session) -> None:
        data = {
            "question_id": session.question_id,
            "learner_state": session.learner_state.model_dump(),
            "history": [entry.model_dump() for entry in session.history],
            "user_id": session.user_id,
            "course_id": session.course_id,
        }
        self._table.put_item(Item={"session_id": session_id, "data": json.dumps(data)})
