"""DynamoStore serialization tests against a fake table: proves the
seam's read/write logic is correct without AWS credentials, a real table
or boto3 even being installed (table is injected, so DynamoStore never
imports boto3 in this test).
"""
import unittest

from backend.app.storage.dynamo import DynamoStore
from backend.app.storage.memory import Session
from contracts.models import HistoryEntry, LearnerState, SkillState


class FakeTable:
    def __init__(self):
        self.items: dict[str, dict] = {}

    def put_item(self, Item):
        self.items[Item["session_id"]] = Item

    def get_item(self, Key):
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

    def test_anonymous_session_has_no_user_id(self):
        session_id = self.store.new_session("q1", LearnerState(skills={}))
        self.assertIsNone(self.store.load_session(session_id).user_id)

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
