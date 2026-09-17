"""Real runtime seams and their combined deadlines, without live AWS calls."""
import asyncio
import copy
import json
import os
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.agents import coordinator as budgets
from backend.app.agents.provider import ProviderError, ProviderResult
from backend.app.agents.real_assessor import RealAssessor
from backend.app.main import create_app
from backend.app.storage.memory import MemoryStore
from backend.app.teaching.tutor import Tutor


class AssessorRuntimeTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {
            "MODEL_PROVIDER": "bedrock", "AWS_REGION": "test", "BEDROCK_MODEL_ID": "test",
            "BEDROCK_TIMEOUT_SECONDS": "15", "DYNAMODB_TABLE_NAME": "",
            "COGNITO_USER_POOL_ID": "", "COGNITO_APP_CLIENT_ID": "",
        })
        env.start()
        self.addCleanup(env.stop)
        self.store = MemoryStore()
        with patch("backend.app.main.MemoryStore", return_value=self.store):
            self.client = TestClient(create_app())
        # Exercise the adapter/deadlines; stub only the synchronous AWS boundary.
        sdk = patch("backend.app.agents.provider._converse", side_effect=self.respond)
        self.converse = sdk.start()
        self.addCleanup(sdk.stop)

    @staticmethod
    def respond(prompt, **kwargs):
        data = json.loads(prompt)
        if "trusted_outcome" in data:
            result = {"misconception_id": next(iter(data["allowed_misconception_ids"]), None),
                      "feedback": "Check each condition separately before relating them."}
        else:
            result = {"text": " ".join(data["authored_content"])}
        return ProviderResult(json.dumps(result), "bedrock", "test", 0)

    def session(self):
        response = self.client.post("/api/v1/sessions", json={})
        self.assertEqual(response.status_code, 201)
        return response.json()

    def answer(self, session, answer="a"):
        return self.client.post("/api/v1/turns", json={
            "session_id": session["session_id"],
            "question_id": session["question"]["question_id"], "answer": answer})

    def test_grade_evidence_and_single_execution_of_each_role(self):
        for answer, outcome, score in [("a", "incorrect", 0), ("b", "correct", 1), ("unsure", "unclear", None)]:
            with self.subTest(answer=answer):
                session = self.session()
                self.converse.reset_mock()
                with patch.object(RealAssessor, "assess", autospec=True, side_effect=RealAssessor.assess) as assess, \
                     patch.object(Tutor, "teach", autospec=True, side_effect=Tutor.teach) as teach:
                    response = self.answer(session, answer)
                self.assertEqual(response.status_code, 200, response.text)
                assess.assert_awaited_once()
                teach.assert_awaited_once()
                assessment = teach.call_args.args[2]
                self.assertEqual((assessment.outcome, assessment.score), (outcome, score))
                stored = self.store.load_session(session["session_id"])
                skill = stored.learner_state.skills[assessment.concept_id]
                self.assertEqual((skill.alpha, skill.beta, skill.evidence_count),
                                 (1 + (score == 1), 1 + (score == 0), int(score is not None)))
                self.assertEqual(stored.history[0].evidence_applied, score is not None)
                self.assertEqual(self.converse.call_count, 0 if score is None else 2)
                self.assertEqual(response.json()["tutor"]["teaching_source"],
                                 "authored_fallback" if score is None else "bedrock")

    def test_failed_diagnosis_keeps_grade_and_tutor_can_generate(self):
        for answer, outcome in [("a", "incorrect"), ("b", "correct")]:
            for failure in [ProviderError("private failure"), TimeoutError("private timeout")]:
                with self.subTest(answer=answer, failure=type(failure).__name__):
                    def respond(prompt, **kwargs):
                        if "trusted_outcome" in json.loads(prompt):
                            raise failure
                        return self.respond(prompt, **kwargs)

                    self.converse.side_effect = respond
                    self.converse.reset_mock()
                    session = self.session()
                    response = self.answer(session, answer)
                    self.assertEqual(response.status_code, 200, response.text)
                    self.assertEqual(response.json()["assessment"]["outcome"], outcome)
                    self.assertNotIn("private", response.text)
                    self.assertEqual(response.json()["tutor"]["teaching_source"], "bedrock")
                    self.assertTrue(self.store.load_session(session["session_id"]).history[0].evidence_applied)
                    self.assertEqual(self.converse.call_count, 2)

    def test_both_provider_timeouts_fit_production_turn_budget(self):
        # Use the actual 4s + 12s caps and 18s deadline. No SDK threads or AWS.
        attempts = []

        async def stalled_worker(function, prompt, **kwargs):
            attempts.append((json.loads(prompt), kwargs["timeout"]))
            await asyncio.Event().wait()

        session = self.session()
        with patch("backend.app.agents.provider.asyncio.to_thread", side_effect=stalled_worker):
            started = time.monotonic()
            response = self.answer(session)
            elapsed = time.monotonic() - started
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["assessment"]["outcome"], "incorrect")
        self.assertEqual(response.json()["tutor"]["teaching_source"], "authored_fallback")
        self.assertTrue(self.store.load_session(session["session_id"]).history[0].evidence_applied)
        self.assertEqual(len(attempts), 2)
        self.assertIn("trusted_outcome", attempts[0][0])
        self.assertIn("authored_content", attempts[1][0])
        self.assertLessEqual(attempts[0][1], budgets.ASSESSOR_BUDGET_SECONDS)
        self.assertLessEqual(attempts[1][1], budgets.TUTOR_BUDGET_SECONDS)
        self.assertLess(elapsed, budgets.TURN_BUDGET_SECONDS)
        self.assertLess(budgets.TURN_BUDGET_SECONDS, 20)

    def test_total_deadline_returns_controlled_error_without_saving_or_retry(self):
        # A replacement seam that ignores provider budgets is still cancelled.
        async def stalled(*args, **kwargs):
            await asyncio.Event().wait()

        session = self.session()
        original = copy.deepcopy(self.store.load_session(session["session_id"]))
        with patch.object(budgets, "TURN_BUDGET_SECONDS", 0.05), \
             patch.object(Tutor, "teach", new=AsyncMock(side_effect=stalled)) as teach:
            started = time.monotonic()
            response = self.answer(session)
            elapsed = time.monotonic() - started
        self.assertEqual(response.status_code, 504)
        self.assertLess(elapsed, 1)
        self.assertEqual(self.store.load_session(session["session_id"]), original)
        teach.assert_awaited_once()
        self.converse.assert_called_once()

    def test_fake_local_full_demo_is_repeatable(self):
        runs = []
        for mode in ["fake", "fake", "local"]:
            with patch.dict(os.environ, {"MODEL_PROVIDER": mode}):
                session = self.session()
                responses = []
                for question_id, answer in [("relationship-q01", "a"), ("relationship-q04", "a"),
                                             ("relationship-q03", "a"), ("relationship-q02", "b")]:
                    self.assertEqual(session["question"]["question_id"], question_id)
                    response = self.answer(session, answer)
                    self.assertEqual(response.status_code, 200, response.text)
                    result = response.json()
                    responses.append({**result, "session_id": "same"})
                    session["question"] = result["next_question"]
                self.assertIsNone(session["question"])
                runs.append(responses)
        self.assertEqual(runs[0], runs[1])
        self.assertEqual(runs[0], runs[2])
        self.converse.assert_not_called()
