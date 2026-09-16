"""Exercise the real production catalog through the default local API composition."""
import itertools
import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.teaching.catalog import Catalog


TARGET = "admissibility_vs_consistency"


class ContentExpansionTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"MODEL_PROVIDER": "fake", "DYNAMODB_TABLE_NAME": "",
                                     "COGNITO_USER_POOL_ID": "", "COGNITO_APP_CLIENT_ID": ""})
        env.start()
        self.addCleanup(env.stop)
        provider = patch("backend.app.teaching.tutor.provider.complete", new_callable=AsyncMock)
        self.complete = provider.start()
        self.addCleanup(provider.stop)
        self.catalog = Catalog()
        self.client = TestClient(create_app())

    def run_sequence(self, outcomes, preferences=None):
        session = self.client.post("/api/v1/sessions", json={}).json()
        question = session["question"]
        seen_questions, seen_candidates, results = set(), set(), []
        evidence = 0
        for outcome in outcomes:
            self.assertIsNotNone(question)
            question_id = question["question_id"]
            self.assertNotIn(question_id, seen_questions)
            seen_questions.add(question_id)
            private = self.catalog.question(question_id)
            answer = ("unsure" if outcome == "unclear" else private.answer_key if outcome == "correct" else
                      next(c.id for c in private.choices if c.id not in {private.answer_key, "unsure"}))
            response = self.client.post("/api/v1/turns", json={
                "session_id": session["session_id"], "question_id": question_id, "answer": answer,
                "presentation_preferences": preferences or {}})
            self.assertEqual(response.status_code, 200, response.text)
            result = response.json()
            results.append(result)
            self.assertEqual(result["assessment"]["outcome"], outcome)
            evidence += int(outcome != "unclear")
            focus = next(c for c in result["concepts"] if c["concept_id"] == TARGET)
            self.assertEqual(focus["evidence_count"], evidence)
            self.assertEqual([c for c in result["concepts"] if c["concept_id"] != TARGET],
                             [c for c in session["concepts"] if c["concept_id"] != TARGET])
            decision = result["decision"]
            question = result["next_question"]
            if decision:
                self.assertNotIn(decision["candidate_id"], seen_candidates)
                seen_candidates.add(decision["candidate_id"])
                selected = next(c for c in self.catalog.candidates if c.candidate_id == decision["candidate_id"])
                self.assertEqual(question["question_id"], selected.next_question_id)
                self.assertEqual(decision["concept_id"], TARGET)
                self.assertTrue(result["tutor"]["text"].strip())
            else:
                self.assertIsNone(question)
            self.assertEqual(result["trace"], ["assess", "update", "select", "teach"])
            self.assertNotIn("answer_key", response.text)
            self.assertNotIn("rubric", response.text)
        self.assertIsNone(question)
        self.assertEqual(seen_questions, set(self.catalog.questions))
        self.assertEqual(seen_candidates, {c.candidate_id for c in self.catalog.candidates})
        self.assertEqual({r["decision"]["kind"] for r in results if r["decision"]},
                         {"diagnostic_probe", "socratic_hint", "worked_example"})
        self.complete.assert_not_called()
        return session, results

    def test_all_answer_paths_use_fresh_questions_and_complete(self):
        for outcomes in itertools.product(("correct", "incorrect", "unclear"), repeat=4):
            with self.subTest(outcomes=outcomes):
                self.run_sequence(outcomes)

    def test_expanded_golden_sequence_preferences_and_reset(self):
        outcomes = ("incorrect", "correct", "correct", "correct")
        session, original = self.run_sequence(outcomes)
        self.assertEqual([r["decision"]["kind"] for r in original if r["decision"]],
                         ["socratic_hint", "diagnostic_probe", "worked_example"])
        self.assertEqual([r["next_question"]["question_id"] for r in original if r["next_question"]],
                         ["relationship-q04", "relationship-q03", "relationship-q02"])
        reset, formatted = self.run_sequence(outcomes, {
            "plain_language": True, "concise": True, "step_by_step": True})
        self.assertNotEqual(reset["session_id"], session["session_id"])
        self.assertEqual(reset["question"], session["question"])
        self.assertEqual(reset["concepts"], session["concepts"])
        for before, after in zip(original, formatted):
            self.assertEqual({k: v for k, v in before.items() if k not in {"session_id", "tutor"}},
                             {k: v for k, v in after.items() if k not in {"session_id", "tutor"}})
            if before["decision"]:
                self.assertNotEqual(before["tutor"]["text"], after["tutor"]["text"])
                self.assertTrue(after["tutor"]["text"].startswith("1. "))


if __name__ == "__main__":
    unittest.main()
