"""One course-bound learner drives both modes. All provider work is mocked."""
import asyncio
from copy import deepcopy
import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from backend.app.agents.provider import ProviderResult
from backend.app.main import create_app
from backend.app.storage.courses import MemoryCourseRegistry
from backend.app.storage.memory import MemoryStore
from backend.app.storage.dynamo import DynamoStore
from backend.tests.storage.test_dynamo import FakeTable
from backend.app.teaching.runtime_catalog import build_runtime_catalog
from backend.app.teaching.targeted_questions import grounding, validate_proposal
from backend.app.teaching.remediation import RemediationFocus

FIXTURE = Path(__file__).resolve().parents[2] / "backend/tests/ingestion/fixtures/grad-algorithms.pptx"


def proposal_for(payload):
    ref = payload["sources"][0]
    return {"prompt": "Which statement explains the relationship described in the reading?",
            "choices": [{"id": "a", "text": ref["quote"]},
                        {"id": "b", "text": "Every problem requires independent exhaustive enumeration."},
                        {"id": "c", "text": "Subproblems never share any useful results."}],
            "correct_choice_id": "a", "rubric": ref["quote"],
            "source_reference_id": ref["source_reference_id"]}


class RemediationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.registry = MemoryCourseRegistry()
        self.calls = []
        self.provider = AsyncMock(side_effect=self.respond)
        for patcher in (
            patch.dict(os.environ, {"MODEL_PROVIDER": "fake", "DYNAMODB_TABLE_NAME": "",
                                   "COGNITO_USER_POOL_ID": "", "COGNITO_APP_CLIENT_ID": ""}),
            patch("backend.app.main.MemoryStore", return_value=self.store),
            patch("backend.app.agents.provider.complete", self.provider),
            patch("backend.app.agents.provider._converse", side_effect=AssertionError("No live AWS")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(create_app(course_registry=self.registry))
        self.course = self.upload("Algorithms")

    def upload(self, title):
        result = self.client.post("/api/v1/courses", data={"title": title},
                                  files=[("files", (FIXTURE.name, FIXTURE.read_bytes()))])
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    def start(self, course=None):
        result = self.client.post("/api/v1/sessions", json={"course_id": (course or self.course)["course_id"]})
        self.assertEqual(result.status_code, 201, result.text)
        return result.json()

    def answer(self, session, question=None, answer="b"):
        question = question or session["question"]
        return self.client.post("/api/v1/turns", json={"session_id": session["session_id"],
                                "question_id": question["question_id"], "answer": answer})

    def respond(self, prompt, **kwargs):
        data = json.loads(prompt)
        self.calls.append(data)
        if data.get("task") == "targeted_remediation":
            self.assertIn("response_schema", kwargs)
            output = proposal_for(data)
        elif "trusted_outcome" in data:
            output = {"misconception_id": None, "feedback": "Review the conditions in the reading."}
        else:
            output = {"text": " ".join(data["authored_content"])}
        return ProviderResult(json.dumps(output), "bedrock", "mock", 0)

    def test_uploaded_course_shared_focus_generated_grading_and_session_isolation(self):
        session, peer = self.start(), self.start()
        other = self.start(self.upload("Another course"))
        before = deepcopy(self.store.sessions)
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
            response = self.answer(session)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        stored = self.store.load_session(session["session_id"])
        cid = session["question"]["concept_id"]
        self.assertEqual(stored.learner_state.skills[cid].beta, 2)
        self.assertEqual(stored.remediation_focus.concept_id, cid)
        self.assertIsNone(stored.remediation_focus.misconception_id)
        self.assertEqual(body["next_question"]["concept_id"], cid)
        self.assertEqual(body["flashcards"][0]["concept_id"], cid)
        self.assertEqual(len(stored.generated_questions), 1)
        record = stored.generated_questions[body["next_question"]["question_id"]]
        self.assertEqual(record.question.answer_key, "a")
        self.assertTrue(record.question.rubric)
        self.assertNotEqual(body["next_question"]["question_id"], session["question"]["question_id"])
        self.assertEqual(set(body["next_question"]), {"question_id", "concept_id", "prompt", "choices"})
        self.assertNotIn("remediation_focus", body)
        self.assertNotIn("source_quote", response.text)
        self.assertNotIn("correct_choice_id", response.text)
        targeted = [data for data in self.calls if data.get("task") == "targeted_remediation"]
        self.assertEqual(len(targeted), 1)
        self.assertEqual(self.provider.await_count, 3)
        focus = stored.remediation_focus
        refs = grounding(build_runtime_catalog(self.registry.get(self.course["course_id"])), focus)
        self.assertEqual([s["quote"] for s in targeted[0]["sources"]], [r.quote for r in refs.values()])
        self.assertNotIn(other["course_id"], json.dumps(targeted))
        for untouched in (peer, other):
            self.assertEqual(self.store.load_session(untouched["session_id"]), before[untouched["session_id"]])
            self.assertEqual(self.answer(untouched, body["next_question"]).status_code, 400)
        runtime = build_runtime_catalog(self.registry.get(self.course["course_id"]))
        self.assertNotIn(record.question.question_id, runtime.questions)
        # Trusted key grades the new item with zero provider calls in local mode.
        self.provider.reset_mock()
        second = self.answer(session, body["next_question"], "a")
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["assessment"]["outcome"], "correct")
        updated = self.store.load_session(session["session_id"])
        self.assertEqual((updated.learner_state.skills[cid].alpha,
                          updated.learner_state.skills[cid].evidence_count), (2, 2))
        self.assertIsNone(updated.remediation_focus)
        self.provider.assert_not_called()
        self.assertEqual(self.answer(session, body["next_question"], "a").status_code, 400)
        # Replacement slots preserve finite progression and question count.
        next_question = second.json()["next_question"]
        seen = {session["question"]["question_id"], body["next_question"]["question_id"]}
        while next_question:
            self.assertNotIn(next_question["question_id"], seen)
            seen.add(next_question["question_id"])
            self.assertLessEqual(len(seen), session["question_count"])
            result = self.answer(session, next_question, "unsure")
            self.assertEqual(result.status_code, 200, result.text)
            next_question = result.json()["next_question"]
        self.assertEqual(len(seen), session["question_count"])

    def test_correct_unsure_and_local_do_not_generate(self):
        for mode, answer in (("bedrock", "a"), ("bedrock", "unsure"), ("fake", "b"), ("local", "b")):
            session = self.start()
            self.calls.clear()
            self.provider.reset_mock()
            with patch.dict(os.environ, {"MODEL_PROVIDER": mode}):
                response = self.answer(session, answer=answer)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertFalse(any(d.get("task") == "targeted_remediation" for d in self.calls))
            stored = self.store.load_session(session["session_id"])
            self.assertFalse(stored.generated_questions)
            if answer == "unsure":
                self.assertIsNone(stored.remediation_focus)
                self.assertTrue(all(s.evidence_count == 0 for s in stored.learner_state.skills.values()))
            if mode in {"fake", "local"}:
                self.provider.assert_not_called()

    def test_consecutive_replacements_preserve_answered_history_keys_and_provenance(self):
        def fresh_response(prompt, **kwargs):
            result = self.respond(prompt, **kwargs)
            if json.loads(prompt).get("task") == "targeted_remediation":
                proposal = json.loads(result.text)
                proposal["prompt"] = f"Which source statement supports review task {len(self.calls)}?"
                result.text = json.dumps(proposal)
            return result
        self.provider.side_effect = fresh_response
        session = self.start()
        question = session["question"]
        course = self.registry.get(self.course["course_id"])
        for index in range(2):
            before = deepcopy(self.store.load_session(session["session_id"]))
            prior_runtime = build_runtime_catalog(course)
            prior_runtime.apply_session_questions(before.generated_questions)
            with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
                response = self.answer(session, question, "b")
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["assessment"]["outcome"], "incorrect")
            stored = self.store.load_session(session["session_id"])
            self.assertEqual(stored.history[:-1], before.history)
            self.assertEqual(stored.history[-1].question_id, question["question_id"])
            self.assertEqual(len(stored.generated_questions), index + 1)
            runtime = build_runtime_catalog(course)
            runtime.apply_session_questions(stored.generated_questions)
            self.assertEqual(len(runtime.questions), session["question_count"])
            answered = {entry.question_id for entry in stored.history}
            for qid in answered:
                self.assertEqual(runtime.question(qid), prior_runtime.question(qid))
                self.assertEqual(runtime.question_provenance[qid], prior_runtime.question_provenance[qid])
            for qid, record in stored.generated_questions.items():
                self.assertNotIn(record.replaces_question_id, answered)
                self.assertEqual(runtime.question(qid), record.question)
                ref, = runtime.question_provenance[qid]
                self.assertEqual((ref.chunk_id, ref.quote), (record.source_chunk_id, record.source_quote))
            for qid, record in before.generated_questions.items():
                self.assertEqual(stored.generated_questions[qid], record)
            availability = runtime.eligible_candidates(current_question_id=stored.question_id,
                consumed_question_ids=answered,
                consumed_candidate_ids=[entry.candidate_id for entry in stored.history if entry.candidate_id])
            self.assertTrue(all(c.next_question_id not in answered for c in availability.candidates))
            self.assertNotIn(availability.next_concept_question_id, answered)
            question = response.json()["next_question"]
        # A third turn grades the second generated key without any provider work.
        self.provider.reset_mock()
        response = self.answer(session, question, "a")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["assessment"]["outcome"], "correct")
        self.provider.assert_not_called()
        skill = self.store.load_session(session["session_id"]).learner_state.skills[question["concept_id"]]
        self.assertEqual((skill.alpha, skill.beta, skill.evidence_count), (2, 3, 3))

    def test_generation_errors_invalid_content_and_timeout_preserve_fallback(self):
        async def respond(prompt, **kwargs):
            data = json.loads(prompt)
            if data.get("task") == "targeted_remediation":
                if failure == "timeout":
                    await asyncio.Event().wait()
                if failure == "error":
                    raise RuntimeError("private provider error")
                return ProviderResult('{"concept_id":"foreign"}', "bedrock", "mock", 0)
            return self.respond(prompt, **kwargs)
        self.provider.side_effect = respond
        for failure in ("timeout", "error", "invalid"):
            fallback_session = self.start()
            expected = self.answer(fallback_session).json()
            session = self.start()
            self.provider.reset_mock()
            with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}), \
                 patch("backend.app.teaching.targeted_questions.GENERATION_BUDGET_SECONDS", .03):
                response = self.answer(session)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(self.provider.await_count, 3)
            self.assertTrue(response.json()["tutor"]["text"])
            for field in ("next_question", "decision", "concepts"):
                self.assertEqual(response.json()[field], expected[field])
            stored = self.store.load_session(session["session_id"])
            self.assertFalse(stored.generated_questions)
            runtime = build_runtime_catalog(self.registry.get(self.course["course_id"]))
            self.assertIn(response.json()["next_question"]["question_id"], runtime.questions)
            self.assertEqual(response.json()["flashcards"][0]["concept_id"], session["question"]["concept_id"])

    def test_tutor_and_generation_overlap_and_total_timeout_saves_nothing(self):
        events = {"tutor": asyncio.Event(), "generator": asyncio.Event()}
        async def respond(prompt, **kwargs):
            data = json.loads(prompt)
            if "trusted_outcome" not in data:
                stage = "generator" if data.get("task") else "tutor"
                other = "tutor" if stage == "generator" else "generator"
                events[stage].set()
                await asyncio.wait_for(events[other].wait(), .5)
            return self.respond(prompt, **kwargs)
        self.provider.side_effect = respond
        session = self.start()
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
            result = self.answer(session)
        self.assertEqual(result.status_code, 200)
        self.assertTrue(self.store.load_session(session["session_id"]).generated_questions)
        self.assertEqual(result.json()["tutor"]["teaching_source"], "bedrock")
        async def stall(*args, **kwargs):
            await asyncio.Event().wait()
        self.provider.side_effect = stall
        session = self.start()
        before = deepcopy(self.store.load_session(session["session_id"]))
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}), \
             patch("backend.app.agents.coordinator.TURN_BUDGET_SECONDS", .02):
            result = self.answer(session)
        self.assertEqual(result.status_code, 504)
        self.assertEqual(self.store.load_session(session["session_id"]), before)

    def test_validation_rejects_authority_leaks_duplicates_and_ungrounded_answers(self):
        runtime = build_runtime_catalog(self.registry.get(self.course["course_id"]))
        first = runtime.question(runtime.first_question_id)
        focus = RemediationFocus(course_id=self.course["course_id"], concept_id=first.concept_id,
                                 misconception_id=None, triggering_question_id=first.question_id)
        refs = grounding(runtime, focus)
        replaces = next(q.question_id for q in runtime.questions.values()
                        if q.concept_id == first.concept_id and q.question_id != first.question_id)
        valid = proposal_for({"sources": [{"source_reference_id": k, "quote": r.quote} for k, r in refs.items()]})
        record = validate_proposal(json.dumps(valid), runtime, focus, replaces, refs)
        self.assertEqual(record.question.concept_id, focus.concept_id)
        variants = [dict(valid, concept_id="other"), dict(valid, prompt=first.prompt),
                    dict(valid, prompt="  " + first.prompt.upper() + "  "),
                    dict(valid, source_reference_id="foreign"), dict(valid, correct_choice_id="unsure"),
                    dict(valid, rubric="Invented justification"), dict(valid, prompt=focus.concept_id),
                    dict(valid, prompt="The correct answer is a."),
                    dict(valid, prompt=valid["choices"][0]["text"])]
        for invalid in variants:
            with self.subTest(invalid=invalid), self.assertRaises((ValueError, KeyError)):
                validate_proposal(json.dumps(invalid), runtime, focus, replaces, refs)
        for choices in ([valid["choices"][0], valid["choices"][0]],
                        [{"id": "a", "text": "An invented source answer"}, valid["choices"][1]]):
            with self.assertRaises(ValueError):
                validate_proposal(json.dumps(dict(valid, choices=choices)), runtime, focus, replaces, refs)
        with self.assertRaises(ValueError):
            validate_proposal(json.dumps(valid), runtime, focus, first.question_id, refs)
        with self.assertRaises(ValueError):
            validate_proposal(json.dumps(valid), runtime, focus.model_copy(update={"course_id": "foreign"}), replaces, refs)

    def test_private_overlay_and_focus_roundtrip_through_dynamo(self):
        session = self.start()
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
            self.assertEqual(self.answer(session).status_code, 200)
        original = self.store.load_session(session["session_id"])
        dynamo = DynamoStore(FakeTable())
        dynamo.save_session(session["session_id"], original)
        self.assertEqual(dynamo.load_session(session["session_id"]), original)

    def test_missing_grounding_and_completed_course_never_attempt_generation(self):
        session = self.start()
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}), \
             patch("backend.app.teaching.targeted_questions.grounding", return_value={}):
            result = self.answer(session)
        self.assertEqual(result.status_code, 200)
        self.assertFalse(any(c.get("task") == "targeted_remediation" for c in self.calls))
        question = result.json()["next_question"]
        # Reach the final bank item using local, unscored evidence.
        for _ in range(session["question_count"] - 3):
            question = self.answer(session, question, "unsure").json()["next_question"]
        question = self.answer(session, question, "unsure").json()["next_question"]
        self.calls.clear()
        runtime = build_runtime_catalog(self.registry.get(self.course["course_id"]))
        last = runtime.question(question["question_id"])
        wrong = next(c.id for c in last.choices if c.id not in {last.answer_key, "unsure"})
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
            result = self.answer(session, question, wrong)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIsNone(result.json()["next_question"])
        self.assertFalse(any(c.get("task") == "targeted_remediation" for c in self.calls))

    def test_trusted_specific_focus_reaches_generator_without_becoming_public(self):
        # Uploaded RealAssessor currently abstains from naming misconceptions.
        # Exercise a future reviewed rule at the existing trusted assessor seam.
        from backend.app.agents.real_assessor import RealAssessor
        from contracts.models import Assessment
        session = self.start()
        trusted = Assessment(outcome="incorrect", score=0, concept_id=session["question"]["concept_id"],
                             misconception_id="reviewed_test_pattern", feedback="Review the relationship.")
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}), \
             patch.object(RealAssessor, "assess", new=AsyncMock(return_value=trusted)):
            result = self.answer(session)
        self.assertEqual(result.status_code, 200)
        proposal = next(d for d in self.calls if d.get("task") == "targeted_remediation")
        self.assertEqual(proposal["focus"]["misconception_id"], trusted.misconception_id)
        # Existing assessment contract may show a reviewed diagnosis; the new
        # question and cards never expose it or the private focus.
        self.assertNotIn(trusted.misconception_id, json.dumps(result.json()["next_question"]))
        self.assertNotIn(trusted.misconception_id, json.dumps(result.json()["flashcards"]))
        self.assertEqual(result.json()["flashcards"][0]["concept_id"], trusted.concept_id)
