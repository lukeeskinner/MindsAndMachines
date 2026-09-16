import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, Mock, patch
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.agents.coordinator import Coordinator
from backend.app.agents.assessor import FakeAssessor
from backend.app.learner.fake import FakeLearner
from backend.app.policy.fake import FakePolicy
from backend.app.policy.adaptive import AdaptivePolicy
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.fake import FakeTutor
from contracts.models import Assessment, TeachingResult

TARGET = "admissibility_vs_consistency"
FIXTURE = Path(__file__).resolve().parents[2] / "contracts" / "fixtures" / "turn_response.json"


def target(response):
    return next(c for c in response["concepts"] if c["concept_id"] == TARGET)


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app())

    def new_session(self, client=None):
        response = (client or self.client).post("/api/v1/sessions", json={})
        self.assertEqual(response.status_code, 201)
        return response.json()

    def answer(self, session, choice, preferences=None, client=None):
        body = {"session_id": session["session_id"],
                "question_id": session["question"]["question_id"], "answer": choice}
        if preferences is not None:
            body["presentation_preferences"] = preferences
        response = (client or self.client).post("/api/v1/turns", json=body)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_golden_loop_fixture_and_reset(self):
        session = self.new_session()
        self.assertEqual(len(session["concepts"]), 6)
        for c in session["concepts"]:
            self.assertEqual((c["mean"], c["interval90"], c["evidence_count"]),
                             (0.5, {"lower": 0.05, "upper": 0.95}, 0))
        first = self.answer(session, "a")
        self.assertEqual({**first, "session_id": "example-session"}, json.loads(FIXTURE.read_text()))
        second = self.answer({"session_id": session["session_id"], "question": first["next_question"]}, "b")
        self.assertEqual(second["assessment"]["outcome"], "correct")
        self.assertEqual(target(second), {"concept_id": TARGET, "mean": 0.5,
            "interval90": {"lower": 0.1354, "upper": 0.8646}, "evidence_count": 2})
        self.assertIsNone(second["next_question"])
        self.assertIsNone(second["decision"])
        self.assertEqual(second["trace"], ["assess", "update", "select", "teach"])
        untouched = lambda result: [c for c in result["concepts"] if c["concept_id"] != TARGET]
        self.assertEqual(untouched(second), untouched(session))
        reset = self.new_session()
        self.assertNotEqual(reset["session_id"], session["session_id"])
        self.assertEqual(reset["concepts"], session["concepts"])
        self.assertEqual(reset["question"], session["question"])
        self.assertNotIn("answer_key", json.dumps(first))
        self.assertNotIn("rubric", json.dumps(first))

    def test_preferences_change_only_teaching(self):
        original = self.answer(self.new_session(), "a")
        # Three controls plus their useful short-numbered-steps combination, not a full matrix.
        for prefs in [{"plain_language": True}, {"step_by_step": True}, {"concise": True},
                      {"plain_language": True, "step_by_step": True, "concise": True}]:
            with self.subTest(preferences=prefs):
                formatted = self.answer(self.new_session(), "a", prefs)
                self.assertNotEqual(formatted["tutor"]["text"], original["tutor"]["text"])
                self.assertEqual({k: v for k, v in original.items() if k not in {"session_id", "tutor"}},
                                 {k: v for k, v in formatted.items() if k not in {"session_id", "tutor"}})
                self.assertEqual(formatted["tutor"]["fallback"], original["tutor"]["fallback"])
                if prefs.get("step_by_step"):
                    self.assertTrue(formatted["tutor"]["text"].startswith("1. "))

    def test_runtime_policy_receives_posterior_and_learner_keeps_updating(self):
        session = self.new_session()
        with patch.object(AdaptivePolicy, "choose", autospec=True,
                          side_effect=AdaptivePolicy.choose) as choose:
            first = self.answer(session, "a")
        choose.assert_called_once()
        _, concepts, assessment, candidates, history = choose.call_args.args
        self.assertEqual([c.model_dump() for c in concepts], first["concepts"])
        self.assertEqual(assessment.score, 0)
        self.assertEqual(candidates, Catalog().candidates)
        self.assertEqual(history, [])
        self.assertIn(first["decision"]["candidate_id"], [c.candidate_id for c in candidates])
        # A second incorrect answer differs from the fake's canned golden path.
        second = self.answer({"session_id": session["session_id"],
                              "question": first["next_question"]}, "a")
        self.assertEqual(target(second), {"concept_id": TARGET, "mean": 0.25,
            "interval90": {"lower": 0.017, "upper": 0.6316}, "evidence_count": 2})
        self.assertIsNone(second["decision"])
        for result in [first, second]:
            self.assertEqual([c for c in result["concepts"] if c["concept_id"] != TARGET],
                             [c for c in session["concepts"] if c["concept_id"] != TARGET])

    def test_unclear_answer_uses_trivial_fallback_without_evidence(self):
        session = self.new_session()
        response = self.answer(session, "unsure")
        self.assertEqual(response["concepts"], session["concepts"])
        self.assertEqual(response["assessment"]["outcome"], "unclear")
        self.assertTrue(response["tutor"]["fallback"])
        self.assertIn("Let's try another example.", response["tutor"]["text"])

    def test_preferences_require_booleans(self):
        session = self.new_session()
        result = self.client.post("/api/v1/turns", json={
            "session_id": session["session_id"], "question_id": session["question"]["question_id"],
            "answer": "a", "presentation_preferences": {"plain_language": "true"},
        })
        self.assertEqual(result.status_code, 422)

    def test_each_seam_can_be_replaced_without_changing_callers(self):
        catalog = Catalog()
        for seam in ["assessor", "learner", "policy", "teaching"]:
            with self.subTest(seam=seam):
                coordinator = Coordinator(FakeAssessor(), FakeLearner(), FakePolicy(), FakeTutor(catalog))
                if seam == "assessor":
                    replacement = Mock(assess=AsyncMock(return_value=Assessment(
                        outcome="unclear", concept_id=TARGET, score=None,
                        misconception_id=None, feedback="Replacement diagnosis")))
                elif seam == "learner":
                    initial = FakeLearner().initial_state(catalog.concept_ids)
                    replacement = Mock(initial_state=Mock(return_value=initial), update=Mock(return_value=initial))
                elif seam == "policy":
                    replacement = Mock(choose=Mock(return_value=None))
                else:
                    replacement = Mock(teach=AsyncMock(return_value=TeachingResult(
                        text="Replacement teaching", next_question_id="relationship-q02", fallback=False)))
                setattr(coordinator, seam, replacement)
                client = TestClient(create_app(coordinator))
                response = self.answer(self.new_session(client), "a", client=client)
                if seam == "assessor":
                    self.assertEqual(response["assessment"]["feedback"], "Replacement diagnosis")
                elif seam == "learner":
                    self.assertEqual(target(response)["evidence_count"], 0)
                elif seam == "policy":
                    self.assertIsNone(response["decision"])
                    self.assertIsNone(response["next_question"])
                else:
                    self.assertEqual(response["tutor"]["text"], "Replacement teaching")
                self.assertEqual(response["trace"], ["assess", "update", "select", "teach"])


if __name__ == "__main__":
    unittest.main()
