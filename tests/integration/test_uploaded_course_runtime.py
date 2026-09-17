"""Real HTTP composition from source upload through a finite course; AWS is mocked."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.agents.coordinator import Coordinator
from backend.app.agents.provider import ProviderResult
from backend.app.agents.real_assessor import RealAssessor
from backend.app.ingestion import extract_material
from backend.tests.ingestion.helpers import plan_for
from backend.app.learner.bayesian import BayesianLearner
from backend.app.main import create_app
from backend.app.policy.adaptive import AdaptivePolicy
from backend.app.storage.courses import MemoryCourseRegistry
from backend.app.storage.memory import MemoryStore
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.runtime_catalog import build_runtime_catalog
from backend.app.teaching.tutor import Tutor

FIXTURES = Path(__file__).resolve().parents[2] / "backend/tests/ingestion/fixtures"


class UploadedCourseRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.registry = MemoryCourseRegistry()
        self.store = MemoryStore()
        self.coordinator = Coordinator(RealAssessor(), BayesianLearner(), AdaptivePolicy(), Tutor(Catalog()))
        self.provider = AsyncMock(side_effect=AssertionError("Unexpected provider call"))
        for patcher in (
            patch.dict(os.environ, {"MODEL_PROVIDER": "fake", "DYNAMODB_TABLE_NAME": "",
                                   "COGNITO_USER_POOL_ID": "", "COGNITO_APP_CLIENT_ID": ""}),
            patch("backend.app.agents.provider.complete", self.provider),
            patch("backend.app.main.MemoryStore", return_value=self.store),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(create_app(self.coordinator, course_registry=self.registry))

    def upload(self, name="course.pptx", title="Grad Algorithms"):
        result = self.client.post("/api/v1/courses", data={"title": title},
                                  files=[("files", (name, (FIXTURES / name).read_bytes()))])
        self.assertEqual(result.status_code, 201, result.text)
        self.assert_private_fields_absent(result.json())
        return result.json()

    def start(self, course):
        result = self.client.post("/api/v1/sessions", json={"course_id": course["course_id"]})
        self.assertEqual(result.status_code, 201, result.text)
        self.assert_private_fields_absent(result.json())
        return result.json()

    def turn(self, session, question, answer):
        return self.client.post("/api/v1/turns", json={"session_id": session["session_id"],
                                 "question_id": question["question_id"], "answer": answer})

    def assert_private_fields_absent(self, value):
        if isinstance(value, dict):
            self.assertTrue(set(value).isdisjoint({
                "answer_key", "rubric", "explanation", "source_refs", "quote", "summary",
                "materials", "metadata", "warnings", "normalized_text", "teaching_id", "requires_review",
            }))
            for item in value.values():
                self.assert_private_fields_absent(item)
        elif isinstance(value, list):
            for item in value:
                self.assert_private_fields_absent(item)

    def test_pdf_and_pptx_through_all_real_seams_for_each_answer_outcome(self):
        for name in ("course.pdf", "course.pptx"):
            public = self.upload(name)
            course = self.registry.get(public["course_id"])
            runtime = build_runtime_catalog(course)
            self.assertEqual(public["title"], "Grad Algorithms")
            self.assertEqual(public["concepts"], [
                {"concept_id": c.concept_id, "display_name": c.name} for c in course.concepts])
            for outcome, mean, evidence in (("incorrect", 1 / 3, 1), ("correct", 2 / 3, 1),
                                             ("unclear", 0.5, 0)):
                with self.subTest(name=name, outcome=outcome):
                    session = self.start(public)
                    question = runtime.question(session["question"]["question_id"])
                    self.assertEqual(session["question"], question.public().model_dump())
                    answer = ("unsure" if outcome == "unclear" else question.answer_key if outcome == "correct"
                              else next(c.id for c in question.choices if c.id not in {question.answer_key, "unsure"}))
                    with patch.object(self.coordinator.assessor, "assess", wraps=self.coordinator.assessor.assess) as assess, \
                            patch.object(self.coordinator.learner, "update", wraps=self.coordinator.learner.update) as update, \
                            patch.object(self.coordinator.policy, "choose", wraps=self.coordinator.policy.choose) as choose:
                        result = self.turn(session, session["question"], answer)
                    self.assertEqual(result.status_code, 200, result.text)
                    body = result.json()
                    assess.assert_awaited_once()
                    update.assert_called_once()
                    choose.assert_called_once()
                    trusted_assessment = update.call_args.args[1]
                    self.assertEqual(trusted_assessment.score, {"correct": 1, "incorrect": 0, "unclear": None}[outcome])
                    self.assertIsNone(trusted_assessment.misconception_id)
                    self.assertEqual(body["assessment"]["outcome"], outcome)
                    self.assertEqual(body["trace"], ["assess", "update", "select", "teach"])
                    for estimate in body["concepts"]:
                        active = estimate["concept_id"] == question.concept_id
                        self.assertAlmostEqual(estimate["mean"], mean if active else 0.5)
                        self.assertEqual(estimate["evidence_count"], evidence if active else 0)
                    candidate = next(c for c in runtime.candidates if c.candidate_id == body["decision"]["candidate_id"])
                    self.assertEqual(body["next_question"]["question_id"], candidate.next_question_id)
                    self.assertNotEqual(body["next_question"]["question_id"], question.question_id)
                    for paragraph in runtime.artifacts[candidate.content_id].paragraphs:
                        self.assertIn(paragraph, body["tutor"]["text"])
                    self.assertIn("Draft course guidance", body["tutor"]["text"])
                    self.assertEqual(body["provider"], "fake")
                    self.assert_private_fields_absent(body)
        self.provider.assert_not_called()

    def test_grad_algorithms_upload_session_and_reset_never_select_demo_content(self):
        public = self.upload("grad-algorithms.pptx")
        course_id = public["course_id"]
        self.assertTrue(course_id.startswith("course_"))
        runtime = build_runtime_catalog(self.registry.get(course_id))
        self.assertEqual(public["title"], "Grad Algorithms")
        self.assertEqual([c["display_name"] for c in public["concepts"]],
                         ["Dynamic programming", "Optimal substructure"])
        for _ in range(2):  # Initial session and reset carry the same course ID.
            session = self.start(public)
            self.assertEqual(session["course_id"], course_id)
            self.assertEqual(self.store.load_session(session["session_id"]).course_id, course_id)
            self.assertEqual(session["question"], runtime.question(runtime.first_question_id).public().model_dump())
            self.assertEqual({c["concept_id"] for c in session["concepts"]}, set(runtime.concept_ids))
            self.assertTrue(set(runtime.questions).isdisjoint(Catalog().questions))
            self.assertNotRegex(json.dumps([public, session]),
                                r"Introduction to AI|Search & heuristics|[Aa]dmissib|[Cc]onsisten")
        self.provider.assert_not_called()

    def test_finite_progression_transitions_and_completion_even_when_unsure(self):
        public = self.upload()
        runtime = build_runtime_catalog(self.registry.get(public["course_id"]))
        session = self.start(public)
        question, seen, concept_order = session["question"], [], []
        for _ in range(public["question_count"]):
            self.assertNotIn(question["question_id"], seen)
            if not concept_order or concept_order[-1] != question["concept_id"]:
                concept_order.append(question["concept_id"])
            result = self.turn(session, question, "unsure")
            self.assertEqual(result.status_code, 200, result.text)
            body = result.json()
            seen.append(question["question_id"])
            self.assertEqual(body["concepts"], session["concepts"])
            if len(seen) < public["question_count"]:
                self.assertIsNotNone(body["next_question"])
                self.assertNotIn("complete", body["tutor"]["text"])
                if body["decision"] is None:
                    expected = next(q for cid in runtime.concept_ids for q in runtime.course.questions
                                    if q.concept_id == cid and q.question_id not in seen)
                    self.assertEqual(body["next_question"]["question_id"], expected.question_id)
                    self.assertNotEqual(body["next_question"]["concept_id"], question["concept_id"])
                    self.assertIn("next concept", body["tutor"]["text"])
            else:
                self.assertIsNone(body["next_question"])
                self.assertIsNone(body["decision"])
                self.assertEqual(body["tutor"]["text"], "This course activity is complete.")
                self.assertFalse(body["tutor"]["fallback"])
            # Even unscored questions cannot be repeated to manufacture evidence.
            replay = self.turn(session, question, "a")
            self.assertEqual(replay.status_code, 400)
            question = body["next_question"]
        self.assertEqual(set(seen), set(runtime.questions))
        self.assertEqual(concept_order, runtime.concept_ids)
        stored = self.store.load_session(session["session_id"])
        self.assertIsNone(stored.question_id)
        self.assertEqual(len(stored.history), public["question_count"])
        self.assertTrue(all(not h.evidence_applied for h in stored.history))
        self.provider.assert_not_called()

    def test_courses_and_sessions_are_isolated_and_demo_is_unchanged(self):
        first, other = self.upload(), self.upload("course.pdf", "Second course")
        one, same, two = self.start(first), self.start(first), self.start(other)
        untouched = deepcopy(self.store.sessions)
        with patch.object(Catalog, "question", side_effect=AssertionError("Demo content lookup")):
            foreign = self.turn(one, two["question"], "a")
            self.assertEqual(foreign.status_code, 400)
            result = self.turn(one, one["question"], "a")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(self.store.load_session(same["session_id"]), untouched[same["session_id"]])
        self.assertEqual(self.store.load_session(two["session_id"]), untouched[two["session_id"]])
        self.assertTrue({c["concept_id"] for c in result.json()["concepts"]}.isdisjoint(
            c["concept_id"] for c in two["concepts"]))
        demo = self.client.post("/api/v1/sessions", json={}).json()
        self.assertIsNone(demo["course_id"])
        self.assertEqual(demo["question"], Catalog().question(Catalog().first_question_id).public().model_dump())
        demo_turn = self.turn(demo, demo["question"], "a")
        self.assertEqual(demo_turn.status_code, 200)
        self.assertEqual(demo_turn.json()["assessment"]["misconception_id"], "admissible_means_consistent")
        self.provider.assert_not_called()

    def test_restart_missing_or_invalid_artifact_never_grades_or_saves(self):
        public = self.upload()
        session = self.start(public)
        before = deepcopy(self.store.load_session(session["session_id"]))
        restarted = TestClient(create_app(self.coordinator))  # Same store, empty new registry.
        result = restarted.post("/api/v1/turns", json={"session_id": session["session_id"],
                                "question_id": session["question"]["question_id"], "answer": "a"})
        self.assertEqual(result.status_code, 404)
        course = self.registry.get(public["course_id"])
        self.registry._courses[course.course_id] = replace(course, teaching=())
        self.assertEqual(self.turn(session, session["question"], "a").status_code, 422)
        self.assertEqual(self.client.post("/api/v1/sessions", json={"course_id": course.course_id}).status_code, 422)
        self.assertEqual(self.store.load_session(session["session_id"]), before)
        self.provider.assert_not_called()

    def test_policy_cannot_end_early_or_select_a_consumed_question(self):
        public = self.upload()
        course = self.registry.get(public["course_id"])
        for invalid in ("stop", "repeat"):
            session = self.start(public)
            before = deepcopy(self.store.load_session(session["session_id"]))
            def choose(concepts, assessment, candidates, history):
                if invalid == "stop":
                    return None
                decision = AdaptivePolicy().choose(concepts, assessment, candidates, history)
                decision.next_question_id = course.questions[0].question_id
                return decision
            with patch.object(self.coordinator.policy, "choose", side_effect=choose):
                result = self.turn(session, session["question"], "a")
            self.assertEqual(result.status_code, 500, result.text)
            self.assertEqual(self.store.load_session(session["session_id"]), before)

    def test_bedrock_upload_and_turn_use_existing_calls_and_trusted_next_question(self):
        proposal = plan_for((extract_material(FIXTURES / "course.pptx"),))
        tutor_prompts = []
        def complete(prompt, **kwargs):
            data = json.loads(prompt)
            if "passages" in data:
                output = proposal
            elif "trusted_outcome" in data:
                output = {"misconception_id": None, "feedback": "Check the relationship described in the material."}
            else:
                tutor_prompts.append(data)
                output = {"text": "Which detail in the passage helps you respond to the task?"}
            return ProviderResult(json.dumps(output), "bedrock", "mock", 0)
        self.provider.side_effect = complete
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
            public = self.upload()
            self.assertEqual(self.provider.await_count, 1)
            session = self.start(public)
            course = self.registry.get(public["course_id"])
            first = course.questions[0]
            wrong = next(c.id for c in first.choices if c.id != first.answer_key)
            result = self.turn(session, session["question"], wrong)
        self.assertEqual(result.status_code, 200, result.text)
        body = result.json()
        self.assertEqual(self.provider.await_count, 3)  # Ingestion + assessor + exactly one Tutor call.
        self.assertEqual(len(tutor_prompts), 1)
        self.assertEqual(body["tutor"]["teaching_source"], "bedrock")
        self.assertEqual(body["provider"], "bedrock")
        self.assertIn("Which detail in the passage", body["tutor"]["text"])
        self.assert_private_fields_absent(body)
        self.assert_private_fields_absent(tutor_prompts)
        # Same policy/evidence/question with deterministic stored teaching.
        local = self.start(public)
        local_result = self.turn(local, local["question"], wrong).json()
        for field in ("concepts", "decision", "next_question"):
            self.assertEqual(body[field], local_result[field])
        self.assertEqual(self.provider.await_count, 3)

    def test_invalid_or_timed_out_tutor_falls_back_without_retry(self):
        public = self.upload()
        for failure in ("invalid", "timeout"):
            session = self.start(public)
            self.provider.reset_mock()
            def complete(prompt, **kwargs):
                if "trusted_outcome" in json.loads(prompt):
                    return ProviderResult('{"misconception_id":null,"feedback":"Review the material."}', "bedrock", "mock", 0)
                if failure == "timeout":
                    raise TimeoutError("private provider error")
                return ProviderResult('{"text":"The answer is a.","next_question_id":"foreign"}', "bedrock", "mock", 0)
            self.provider.side_effect = complete
            with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
                result = self.turn(session, session["question"], "a")
            self.assertEqual(result.status_code, 200, result.text)
            body = result.json()
            self.assertEqual(self.provider.await_count, 2)
            self.assertTrue(body["tutor"]["fallback"])
            self.assertEqual(body["tutor"]["teaching_source"], "authored_fallback")
            self.assertNotIn("private", body["tutor"]["text"])
            self.assertNotIn("The answer is a", body["tutor"]["text"])
            self.assertNotEqual(body["next_question"]["question_id"], session["question"]["question_id"])
            self.assertIn(body["next_question"]["question_id"],
                          {q.question_id for q in self.registry.get(public["course_id"]).questions})


if __name__ == "__main__":
    unittest.main()
