import asyncio
import copy
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from botocore.exceptions import ClientError

from backend.app.agents.assessor import FakeAssessor
from backend.app.agents.coordinator import Coordinator
from backend.app.agents.provider import ProviderError
from backend.app.learner.bayesian import BayesianLearner
from backend.app.main import create_app
from backend.app.policy.adaptive import AdaptivePolicy
from backend.app.storage.memory import MemoryStore
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.tutor import Tutor
from contracts.models import TeachingResult


class TutorRuntimeTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {
            "MODEL_PROVIDER": "bedrock", "AWS_REGION": "us-east-1",
            "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0", "BEDROCK_TIMEOUT_SECONDS": "0.1",
            "DYNAMODB_TABLE_NAME": "", "COGNITO_USER_POOL_ID": "", "COGNITO_APP_CLIENT_ID": "",
        })
        env.start()
        self.addCleanup(env.stop)
        self.catalog = Catalog()
        self.generated = " ".join(self.catalog.teaching["heuristic-distinction-hint"]["standard"])
        sdk = patch("boto3.client")
        self.factory = sdk.start()
        self.addCleanup(sdk.stop)
        self.sdk = self.factory.return_value
        self.sdk.converse.return_value = self.envelope(json.dumps({"text": self.generated}))
        self.store = MemoryStore()
        store_patch = patch("backend.app.main.MemoryStore", return_value=self.store)
        store_patch.start()
        self.addCleanup(store_patch.stop)
        self.client = TestClient(create_app())
        self.session = self.client.post("/api/v1/sessions", json={}).json()

    @staticmethod
    def envelope(text):
        return {"output": {"message": {"content": [{"text": text}]}}}

    def answer(self, question_id="relationship-q01", answer="a", client=None):
        return (client or self.client).post("/api/v1/turns", json={
            "session_id": self.session["session_id"], "question_id": question_id, "answer": answer})

    def test_default_composition_uses_existing_real_tutor_and_current_assessor(self):
        with patch("backend.app.main.Coordinator", wraps=Coordinator) as compose:
            create_app()
        assessor, learner, policy, teaching = compose.call_args.args
        self.assertIs(type(assessor), FakeAssessor)
        self.assertIs(type(learner), BayesianLearner)
        self.assertIs(type(policy), AdaptivePolicy)
        self.assertIs(type(teaching), Tutor)

    def check_turn(self, *, fallback):
        with patch.object(BayesianLearner, "update", autospec=True, side_effect=BayesianLearner.update) as update, \
             patch.object(AdaptivePolicy, "choose", autospec=True, side_effect=AdaptivePolicy.choose) as choose:
            response = self.answer()
        self.assertEqual(response.status_code, 200, response.text)
        update.assert_called_once()
        choose.assert_called_once()
        result = response.json()
        self.assertEqual(result["tutor"]["fallback"], fallback)
        self.assertEqual(result["tutor"]["teaching_source"], "authored_fallback" if fallback else "bedrock")
        self.assertEqual((result["mode"], result["provider"]), ("dummy", "fake") if fallback else ("live", "bedrock"))
        self.assertEqual(result["next_question"]["question_id"], "relationship-q04")
        self.assertEqual(result["decision"]["candidate_id"], "relationship-hint")
        self.sdk.converse.assert_called_once()
        stored = self.store.load_session(self.session["session_id"])
        self.assertEqual(stored.question_id, "relationship-q04")
        self.assertEqual(stored.learner_state.skills["admissibility_vs_consistency"].evidence_count, 1)
        self.assertEqual(len(stored.history), 1)
        self.assertEqual(stored.history[0].candidate_id, result["decision"]["candidate_id"])
        if fallback:
            self.assertEqual(result["tutor"]["text"], "\n\n".join(
                self.catalog.teaching["heuristic-distinction-hint"]["standard"]))
        for question_id, answer, content_id, next_id in [
            ("relationship-q04", "a", "heuristic-distinction-probe", "relationship-q03"),
            ("relationship-q03", "a", "heuristic-distinction", "relationship-q02"),
        ]:
            if not fallback:
                self.sdk.converse.return_value = self.envelope(json.dumps({
                    "text": " ".join(self.catalog.teaching[content_id]["standard"])}))
            response = self.answer(question_id, answer)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["next_question"]["question_id"], next_id)
            self.assertEqual(response.json()["tutor"]["teaching_source"],
                             "authored_fallback" if fallback else "bedrock")
        final = self.answer("relationship-q02", "b")
        self.assertEqual(final.status_code, 200)
        self.assertIsNone(final.json()["next_question"])
        self.assertEqual(final.json()["tutor"]["teaching_source"], "authored")
        self.assertEqual(final.json()["provider"], "fake")
        self.assertEqual(self.sdk.converse.call_count, 3)  # Completion never generates.
        stored = self.store.load_session(self.session["session_id"])
        self.assertEqual(len(stored.history), 4)
        self.assertEqual(stored.learner_state.skills["admissibility_vs_consistency"].evidence_count, 4)
        reset = self.client.post("/api/v1/sessions", json={}).json()
        self.assertNotEqual(reset["session_id"], self.session["session_id"])
        self.assertEqual(reset["concepts"], self.session["concepts"])

    def test_valid_bedrock_full_path(self):
        self.check_turn(fallback=False)

    def test_provider_failure_returns_reviewed_fallback(self):
        self.sdk.converse.side_effect = ProviderError("provider failed")
        self.check_turn(fallback=True)

    def test_timeout_returns_reviewed_fallback(self):
        # Exercise the real provider deadline without occupying a test worker.
        async def stalled_worker(*args, **kwargs):
            self.sdk.converse()
            await asyncio.Event().wait()

        with patch("backend.app.agents.provider.asyncio.to_thread", side_effect=stalled_worker):
            self.check_turn(fallback=True)

    def test_malformed_output_returns_reviewed_fallback(self):
        self.sdk.converse.return_value = self.envelope("not JSON")
        self.check_turn(fallback=True)

    def test_validation_rejection_returns_reviewed_fallback(self):
        self.sdk.converse.return_value = self.envelope(json.dumps({"text": "Every admissible heuristic is consistent."}))
        self.check_turn(fallback=True)

    def test_fake_and_local_are_deterministic_and_never_call_provider(self):
        results = []
        for mode in ["fake", "local"]:
            with patch.dict(os.environ, {"MODEL_PROVIDER": mode}):
                self.session = self.client.post("/api/v1/sessions", json={}).json()
                result = self.answer().json()
                self.assertEqual(result["tutor"]["teaching_source"], "authored")
                self.assertFalse(result["tutor"]["fallback"])
                self.assertNotIn("echo", result["tutor"]["text"])
                results.append({**result, "session_id": "same"})
        self.assertEqual(*results)
        self.factory.assert_not_called()

    def test_unclear_is_reviewed_fallback_without_provider_or_evidence(self):
        result = self.answer(answer="unsure").json()
        self.assertEqual(result["tutor"]["teaching_source"], "authored_fallback")
        self.assertTrue(result["tutor"]["fallback"])
        self.assertEqual(result["concepts"], self.session["concepts"])
        self.factory.assert_not_called()

    def test_integration_errors_are_controlled_and_do_not_save_session(self):
        original = copy.deepcopy(self.store.load_session(self.session["session_id"]))
        bad_result = TeachingResult(text="test", next_question_id="relationship-q01", fallback=False)
        with patch.object(Tutor, "teach", new=AsyncMock(return_value=bad_result)):
            response = self.answer()
        self.assertEqual(response.status_code, 500)
        self.assertIn("configuration error", response.json()["detail"])
        self.assertEqual(self.store.load_session(self.session["session_id"]), original)
        catalog = Catalog()
        del catalog.questions["relationship-q04"]
        with patch("backend.app.main.Catalog", return_value=catalog):
            client = TestClient(create_app())
        response = self.answer(client=client)
        self.assertEqual(response.status_code, 500)
        self.assertIn("configuration error", response.json()["detail"])
        self.assertEqual(self.store.load_session(self.session["session_id"]), original)
        self.factory.assert_not_called()

    def test_server_diagnostics_distinguish_failures_without_logging_secrets(self):
        secret = "DO_NOT_LOG_CREDENTIAL_TOKEN_PROMPT_OR_OUTPUT"
        cases = [
            (None, self.envelope(json.dumps({"text": self.generated})), "accepted", "bedrock"),
            (None, self.envelope(secret), "json_error", "authored_fallback"),
            (None, self.envelope(json.dumps({"text": "Every admissible heuristic is consistent. " + secret})),
             "validation_error", "authored_fallback"),
            (ClientError({"Error": {"Code": "ExpiredTokenException", "Message": secret}}, "Converse"),
             None, "provider_error", "authored_fallback"),
            (ClientError({"Error": {"Code": secret, "Message": secret}}, "Converse"),
             None, "provider_error", "authored_fallback"),
        ]
        with patch.dict(os.environ, {key: secret for key in (
                "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
                "COGNITO_TOKEN", "AUTHORIZATION")}):
            for error, envelope, reason, source in cases:
                with self.subTest(reason=reason), self.assertLogs("uvicorn.error", level="INFO") as captured:
                    self.sdk.converse.reset_mock()
                    self.sdk.converse.side_effect = error
                    self.sdk.converse.return_value = envelope
                    self.client = TestClient(create_app())
                    self.session = self.client.post("/api/v1/sessions", json={}).json()
                    response = self.answer()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["tutor"]["teaching_source"], source)
                self.assertEqual(response.json()["next_question"]["question_id"], "relationship-q04")
                self.sdk.converse.assert_called_once()
                logs = "\n".join(captured.output)
                self.assertIn("runtime_start pid=", logs)
                self.assertIn("configured_provider='bedrock'", logs)
                self.assertIn("configured_model='amazon.nova-lite-v1:0'", logs)
                self.assertIn("provider_attempt pid=", logs)
                self.assertIn("bedrock_converse_started", logs)
                self.assertIn(f"provider_attempted=True teaching_source={source}", logs)
                self.assertIn(f"reason={reason}", logs)
                self.assertNotIn(secret, logs)
                self.assertNotIn(self.generated, logs)
                self.assertNotIn("Traceback", logs)
                if reason == "validation_error":
                    self.assertIn("rule=Teaching exposes or introduces internal IDs", logs)
                if error is None:
                    self.assertIn("bedrock_response_received", logs)
                    self.assertIn("provider_returned", logs)
                else:
                    self.assertNotIn("provider_returned", logs)
            self.assertIn("provider_failed reason=provider_error", logs)

    def test_local_diagnostics_do_not_claim_provider_attempt(self):
        with patch.dict(os.environ, {"MODEL_PROVIDER": "fake"}), \
             self.assertLogs("uvicorn.error", level="INFO") as captured:
            result = self.answer().json()
        self.assertEqual(result["tutor"]["teaching_source"], "authored")
        logs = "\n".join(captured.output)
        self.assertIn("provider_attempted=False teaching_source=authored fallback=False reason=local", logs)
        self.assertNotIn("bedrock_converse_started", logs)
        self.factory.assert_not_called()

    def test_unexpected_validation_exception_text_is_not_logged(self):
        secret = "SECRET_EXCEPTION_CONTENT"
        with patch("backend.app.teaching.tutor._validated_text", side_effect=ValueError(secret)), \
             self.assertLogs("uvicorn.error", level="INFO") as captured:
            response = self.answer()
        self.assertEqual(response.json()["tutor"]["teaching_source"], "authored_fallback")
        logs = "\n".join(captured.output)
        self.assertIn("tutor_validation_rejected rule=unclassified", logs)
        self.assertNotIn(secret, logs)
        self.assertNotIn(secret, response.text)
