"""Course-bound sessions and safe resolution of their private runtime artifacts."""
import asyncio
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from backend.app.agents.coordinator import Coordinator
from backend.app.ingestion import process_course
from backend.app.main import create_app
from backend.app.storage.courses import MemoryCourseRegistry
from backend.app.storage.memory import MemoryStore
from backend.app.teaching.catalog import Catalog


class CourseSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).resolve().parents[2] / "backend/tests/ingestion/fixtures/course.pptx"
        cls.course = asyncio.run(process_course([fixture], title="First course", mode="local"))
        cls.other = asyncio.run(process_course([fixture], title="Second course", mode="local"))

    def setUp(self):
        env = patch.dict(os.environ, {"MODEL_PROVIDER": "fake", "DYNAMODB_TABLE_NAME": "",
                                     "COGNITO_USER_POOL_ID": "", "COGNITO_APP_CLIENT_ID": ""})
        env.start()
        self.addCleanup(env.stop)
        self.registry = MemoryCourseRegistry()
        self.registry.register(self.course)
        self.registry.register(self.other)
        self.store = MemoryStore()
        with patch("backend.app.main.MemoryStore", return_value=self.store):
            self.client = TestClient(create_app(course_registry=self.registry))

    def create(self, course_id):
        response = self.client.post("/api/v1/sessions", json={"course_id": course_id})
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def test_creation_binds_course_and_returns_only_public_preview(self):
        result = self.create(self.course.course_id)
        stored = self.store.load_session(result["session_id"])
        self.assertEqual(stored.course_id, self.course.course_id)
        self.assertEqual(stored.question_id, self.course.questions[0].question_id)
        self.assertEqual(result["course_id"], self.course.course_id)
        self.assertEqual(set(result), {"session_id", "course_id", "question", "concepts"})
        self.assertEqual(set(result["question"]), {"question_id", "concept_id", "prompt", "choices"})
        self.assertEqual(set(stored.learner_state.skills), {c.concept_id for c in self.course.concepts})
        self.assertEqual(stored.history, [])
        for concept in result["concepts"]:
            self.assertEqual(concept["mean"], 0.5)
            self.assertEqual(concept["evidence_count"], 0)
        self.assertIs(self.registry.get(stored.course_id), self.course)

    def test_unknown_or_malformed_course_creates_no_session(self):
        for body, status in [({"course_id": "missing"}, 404), ({"course_id": ""}, 422),
                             ({"course_id": 123}, 422), ({"answer_key": "a"}, 422)]:
            response = self.client.post("/api/v1/sessions", json=body)
            self.assertEqual(response.status_code, status, response.text)
            self.assertEqual(self.store.sessions, {})

    def test_default_app_does_not_share_injected_registry(self):
        response = TestClient(create_app()).post("/api/v1/sessions", json={"course_id": self.course.course_id})
        self.assertEqual(response.status_code, 404)

    def test_demo_empty_null_and_absent_body_remain_compatible(self):
        for request_args in ({"json": {}}, {"json": {"course_id": None}}, {}):
            response = self.client.post("/api/v1/sessions", **request_args)
            self.assertEqual(response.status_code, 201, response.text)
            session = response.json()
            self.assertIsNone(session["course_id"])
            self.assertIsNone(self.store.load_session(session["session_id"]).course_id)
            self.assertEqual(session["question"], Catalog().question(Catalog().first_question_id).public().model_dump())
            turn = self.client.post("/api/v1/turns", json={"session_id": session["session_id"],
                "question_id": session["question"]["question_id"], "answer": "a"})
            self.assertEqual(turn.status_code, 200, turn.text)
            self.assertIsNone(self.store.load_session(session["session_id"]).course_id)

    def test_missing_course_is_rejected_before_coordinator_or_demo_lookup(self):
        session = self.create(self.course.course_id)
        stored = self.store.load_session(session["session_id"])
        before = stored.learner_state.model_dump()
        # Persistent sessions may survive a process-local course registry restart.
        self.registry._courses.clear()
        with patch.object(Coordinator, "run_turn", new_callable=AsyncMock) as run_turn, \
                patch.object(Catalog, "question", side_effect=AssertionError("Demo lookup")):
            for question_id in (stored.question_id, "relationship-q01"):
                result = self.client.post("/api/v1/turns", json={"session_id": session["session_id"],
                    "question_id": question_id, "answer": "a"})
                self.assertEqual(result.status_code, 404)
                self.assertEqual(result.json(), {"detail": "Course not found. Upload the materials again."})
            run_turn.assert_not_called()
        self.assertEqual(stored.learner_state.model_dump(), before)
        self.assertEqual(stored.history, [])

    def test_sessions_share_artifact_but_not_state_and_courses_stay_separate(self):
        first = self.create(self.course.course_id)
        second = self.create(self.course.course_id)
        other = self.create(self.other.course_id)
        self.assertEqual(len({s["session_id"] for s in (first, second, other)}), 3)
        one = self.store.load_session(first["session_id"])
        two = self.store.load_session(second["session_id"])
        self.assertIs(self.registry.get(one.course_id), self.registry.get(two.course_id))
        one.learner_state.skills[self.course.concepts[0].concept_id].alpha = 8
        self.assertEqual(two.learner_state.skills[self.course.concepts[0].concept_id].alpha, 1)
        self.assertNotEqual(first["question"]["question_id"], other["question"]["question_id"])
        self.assertTrue(set(one.learner_state.skills).isdisjoint(
            self.store.load_session(other["session_id"]).learner_state.skills))

    def test_reset_resends_course_id_or_explicitly_returns_to_demo(self):
        original = self.create(self.course.course_id)
        reset = self.create(original["course_id"])
        self.assertNotEqual(reset["session_id"], original["session_id"])
        self.assertEqual({k: v for k, v in reset.items() if k != "session_id"},
                         {k: v for k, v in original.items() if k != "session_id"})
        demo = self.client.post("/api/v1/sessions", json={}).json()
        self.assertIsNone(demo["course_id"])
        self.assertEqual(self.store.load_session(original["session_id"]).course_id, self.course.course_id)
