"""Session-bound chat, provider failure, trusted context and overlapping writes."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from backend.app.agents.provider import ProviderError, ProviderResult
from backend.app.main import create_app
from backend.app.teaching.chat import SYSTEM
from backend.app.storage.memory import MemoryStore


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        for patcher in (patch.dict(os.environ, {"MODEL_PROVIDER": "fake", "DYNAMODB_TABLE_NAME": ""}),
                        patch("backend.app.main.MemoryStore", return_value=self.store)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = create_app()
        self.client = TestClient(self.app)
        fixture = Path("backend/tests/ingestion/fixtures/course.pptx")
        course = self.client.post("/api/v1/courses", data={"title": "Uploaded algorithms"},
                                 files={"files": (fixture.name, fixture.read_bytes())})
        self.assertEqual(course.status_code, 201)
        self.course = course.json()
        self.session = self.client.post("/api/v1/sessions", json={"course_id": self.course["course_id"]}).json()
        self.sid = self.session["session_id"]

    def chat(self, **overrides):
        return self.client.post("/api/v1/chat", json={"session_id": self.sid, "message": "Explain this concept", **overrides})

    def test_live_context_history_and_reset_are_server_owned(self):
        before = deepcopy(self.store.load_session(self.sid))
        complete = AsyncMock(return_value=ProviderResult('{"text":"A source-grounded explanation."}', "bedrock", "test", 1))
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}), patch("backend.app.agents.provider.complete", complete):
            for _ in range(2):
                response = self.chat()
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()["teaching_source"], "bedrock")
            first = json.loads(complete.call_args_list[0].args[0])
            second = json.loads(complete.call_args_list[1].args[0])
            self.assertEqual(first["course"], "Uploaded algorithms")
            self.assertEqual(first["conversation"], [])
            self.assertEqual(len(second["conversation"]), 1)
            for private in ("answer_key", "rubric", "question_id", "course_id", "concept_id", "alpha", "beta"):
                self.assertNotIn(f'"{private}"', complete.call_args.args[0])
            fresh = self.client.post("/api/v1/sessions", json={"course_id": self.course["course_id"]}).json()
            self.chat(session_id=fresh["session_id"])
            self.assertEqual(json.loads(complete.call_args.args[0])["conversation"], [])
        after = self.store.load_session(self.sid)
        self.assertEqual(after.learner_state, before.learner_state)
        self.assertEqual(after.history, before.history)
        self.assertEqual(after.question_id, before.question_id)
        self.assertEqual(len(after.chat_history), 2)

    def test_chat_survives_turn_and_uses_updated_evidence(self):
        self.assertEqual(self.chat().status_code, 200)
        q = self.session["question"]
        response = self.client.post("/api/v1/turns", json={"session_id": self.sid, "question_id": q["question_id"], "answer": q["choices"][0]["id"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.store.load_session(self.sid).chat_history), 1)
        complete = AsyncMock(return_value=ProviderResult('{"text":"Let us review."}', "bedrock", "test", 1))
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}), patch("backend.app.agents.provider.complete", complete):
            self.assertEqual(self.chat().status_code, 200)
        payload = json.loads(complete.call_args.args[0])
        self.assertEqual(sum(n["observations"] for n in payload["study_notes"]), 1)

    def test_rejects_injected_identity_empty_unknown_and_provider_failure(self):
        self.assertEqual(self.chat(course_id="forged").status_code, 422)
        self.assertEqual(self.chat(message="  ").status_code, 422)
        self.assertEqual(self.chat(message="x" * 2001).status_code, 422)
        self.assertEqual(self.chat(session_id="missing").status_code, 404)
        before = deepcopy(self.store.load_session(self.sid))
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
            for reply in (ProviderError("private exception"), ProviderResult('{"text":""}', "bedrock", "test", 1),
                          ProviderResult('{"text":"ok", "answer_key":"a"}', "bedrock", "test", 1),
                          ProviderResult('{"text":"ok"}', "fake", "test", 1),
                          ProviderResult('{"text":"first","text":"last"}', "bedrock", "test", 1),
                          ProviderResult(json.dumps({"text": SYSTEM}), "bedrock", "test", 1),
                          ProviderResult('{"text":"I increased your mastery to 100%."}', "bedrock", "test", 1),
                          ProviderResult('{"text":"The correct answer is A."}', "bedrock", "test", 1)):
                mock = AsyncMock(side_effect=reply) if isinstance(reply, Exception) else AsyncMock(return_value=reply)
                with patch("backend.app.agents.provider.complete", mock):
                    result = self.chat()
                self.assertEqual(result.status_code, 503)
                self.assertNotIn("private exception", result.text)
                self.assertEqual(self.store.load_session(self.sid), before)
        self.assertEqual(self.chat().status_code, 200)  # failed requests release the guard

    def test_missing_course_never_uses_demo(self):
        self.store.load_session(self.sid).course_id = "missing"
        with patch("backend.app.agents.provider.complete") as complete:
            self.assertEqual(self.chat().status_code, 404)
            complete.assert_not_called()

    def test_completion_and_bounded_history(self):
        self.store.load_session(self.sid).question_id = None
        for _ in range(15):
            self.assertEqual(self.chat().status_code, 200)
        self.assertEqual(len(self.store.load_session(self.sid).chat_history), 12)
        self.assertEqual(self.store.load_session(self.sid).history, [])

    def test_overlapping_chat_and_turn_cannot_clobber_state(self):
        async def run():
            started, release = asyncio.Event(), asyncio.Event()
            async def slow(*args, **kwargs):
                started.set()
                await release.wait()
                return ProviderResult('{"text":"A helpful explanation."}', "bedrock", "test", 1)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url="http://test") as client:
                with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}), patch("backend.app.agents.provider.complete", slow):
                    pending = asyncio.create_task(client.post("/api/v1/chat", json={"session_id": self.sid, "message": "Explain"}))
                    await started.wait()
                    duplicate = await client.post("/api/v1/chat", json={"session_id": self.sid, "message": "Explain"})
                    turn = await client.post("/api/v1/turns", json={"session_id": self.sid, "question_id": self.session["question"]["question_id"], "answer": "unsure"})
                    release.set()
                    self.assertEqual((await pending).status_code, 200)
                    self.assertEqual(duplicate.status_code, 409)
                    self.assertEqual(turn.status_code, 409)
            self.assertEqual(len(self.store.load_session(self.sid).chat_history), 1)
            self.assertEqual(self.store.load_session(self.sid).history, [])
        asyncio.run(run())
