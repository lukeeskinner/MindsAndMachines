"""DynamoStore serialization tests against a fake table: proves the
seam's read/write logic is correct without AWS credentials, a real table
or boto3 even being installed (table is injected, so DynamoStore never
imports boto3 in this test).
"""
import json
import unittest

from backend.app.storage.dynamo import DynamoStore
from backend.app.storage.memory import Session
from contracts.models import ChatExchange, HistoryEntry, LearnerState, SkillState


class FakeTable:
    def __init__(self):
        self.items: dict[str, dict] = {}
        from types import SimpleNamespace
        self.name = "test"
        self.meta = SimpleNamespace(client=self)

    def transact_write_items(self, TransactItems):
        for entry in TransactItems:
            self.put_item(entry["Put"]["Item"])


    def put_item(self, Item):
        self.items[Item["session_id"]] = Item

    def get_item(self, Key, **kwargs):
        item = self.items.get(Key["session_id"])
        return {"Item": item} if item is not None else {}


class DynamoStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = DynamoStore(table=FakeTable())

    def test_round_trips_a_new_session(self):
        state = LearnerState(skills={"bfs": SkillState(alpha=1, beta=1, evidence_count=0)})
        session_id = self.store.new_session("q1", state, user_id="user-abc")
        loaded = self.store.load_session(session_id)
        self.assertEqual(loaded.question_id, "q1")
        self.assertEqual(loaded.user_id, "user-abc")
        self.assertEqual(loaded.learner_state, state)
        self.assertEqual(loaded.history, [])

    def test_chat_round_trip_and_legacy_default(self):
        sid = self.store.new_session("q1", LearnerState(skills={}))
        session = self.store.load_session(sid)
        session.chat_history = [ChatExchange(message="Explain", text="Study notes", teaching_source="authored")]
        self.store.save_session(sid, session)
        self.assertEqual(self.store.load_session(sid).chat_history, session.chat_history)
        item = self.store._table.items[sid]
        data = json.loads(item["data"])
        del data["chat_history"]
        item["data"] = json.dumps(data)
        self.assertEqual(self.store.load_session(sid).chat_history, [])

    def test_anonymous_session_has_no_user_id(self):
        session_id = self.store.new_session("q1", LearnerState(skills={}))
        self.assertIsNone(self.store.load_session(session_id).user_id)
        self.assertIsNone(self.store.load_session(session_id).course_id)

    def test_course_reference_round_trips_without_storing_artifact(self):
        session_id = self.store.new_session("course-q1", LearnerState(skills={}),
                                            user_id="user-abc", course_id="course-1")
        session = self.store.load_session(session_id)
        self.assertEqual(session.course_id, "course-1")
        self.assertEqual(session.user_id, "user-abc")
        session.question_id = None
        self.store.save_session(session_id, session)
        self.assertEqual(self.store.load_session(session_id).course_id, "course-1")
        data = json.loads(self.store._table.items[session_id]["data"])
        self.assertEqual(set(data), {"question_id", "learner_state", "history", "user_id", "course_id",
                                     "remediation_focus", "generated_questions", "chat_history",
                                     "profile_id", "session_start", "budget", "current_review"})

    def test_legacy_session_without_course_id_still_loads(self):
        session_id = self.store.new_session("q1", LearnerState(skills={}))
        item = self.store._table.items[session_id]
        data = json.loads(item["data"])
        del data["course_id"]
        del data["remediation_focus"]
        del data["generated_questions"]
        item["data"] = json.dumps(data)
        self.assertIsNone(self.store.load_session(session_id).course_id)

    def test_save_updates_the_same_session(self):
        state = LearnerState(skills={})
        session_id = self.store.new_session("q1", state)
        entry = HistoryEntry(question_id="q1", evidence_applied=True, candidate_id="c1")
        self.store.save_session(session_id, Session("q2", state, [entry], None))
        loaded = self.store.load_session(session_id)
        self.assertEqual(loaded.question_id, "q2")
        self.assertEqual(loaded.history, [entry])

    def test_missing_session_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.store.load_session("does-not-exist")


if __name__ == "__main__":
    unittest.main()
