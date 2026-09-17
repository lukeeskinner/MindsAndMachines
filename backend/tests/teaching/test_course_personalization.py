"""Mocked uploaded-course Tutor generation; no live provider or extra ingestion."""
import asyncio
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.agents.provider import ProviderError, ProviderResult
from backend.app.ingestion import process_course
from backend.tests.ingestion.helpers import plan_for
from backend.app.learner.bayesian import BayesianLearner
from backend.app.teaching.runtime_catalog import build_runtime_catalog
from backend.app.teaching.tutor import MAX_TEXT_LENGTH, Tutor
from backend.tests.teaching.test_runtime_catalog import synthetic_course
from contracts.models import Assessment, Decision, LearnerPresentationPreferences


FIXTURE = Path(__file__).resolve().parents[1] / "ingestion/fixtures/course.pptx"


class CoursePersonalizationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.course = asyncio.run(process_course([FIXTURE], mode="local"))

    def setUp(self):
        self.catalog = build_runtime_catalog(self.course)
        self.estimates = BayesianLearner().initial_state(self.catalog.concept_ids).concepts
        self.preferences = LearnerPresentationPreferences()
        self.select("diagnostic_probe")
        self.complete = AsyncMock()
        for patcher in (patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}),
                        patch("backend.app.agents.provider.complete", self.complete)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.respond("What detail from the material would you use here?")

    def select(self, kind):
        candidate = next(c for c in self.catalog.candidates if c.kind == kind)
        self.decision = Decision(**candidate.model_dump(), reason="Authoritative priority 0.7500")
        self.assessment = Assessment(outcome="incorrect", concept_id=candidate.concept_id,
                                     score=0, misconception_id=None, feedback="PRIVATE diagnosis")

    def respond(self, text):
        self.complete.return_value = ProviderResult(json.dumps({"text": text}), "bedrock", "mock", 0)

    async def teach(self):
        return await Tutor(self.catalog).teach(self.decision, self.assessment, self.estimates, self.preferences)

    def stored(self):
        return self.catalog.render(self.decision, self.assessment, self.estimates, self.preferences)

    async def assert_fallback(self):
        self.complete.reset_mock()
        expected = self.stored()
        result = await self.teach()
        self.assertEqual(result.text, expected.text)
        self.assertEqual(result.next_question_id, self.decision.next_question_id)
        self.assertTrue(result.fallback)
        self.assertEqual(result.teaching_source, "authored_fallback")
        self.complete.assert_awaited_once()
        return result

    async def test_valid_personalization_for_each_kind_uses_exactly_one_call(self):
        versions = {
            "diagnostic_probe": "Which detail in the passage helps you respond to the task?",
            "socratic_hint": "Find the condition or relationship in the passage. Which part of the task relies on it?",
            "worked_example": "First, find what the task asks you to look for. "
                              "Next, separate the passage's condition from its consequence. "
                              "Finally, compare the responses with that relationship and rule out unsupported claims.",
        }
        for kind, text in versions.items():
            with self.subTest(kind=kind):
                self.select(kind)
                self.complete.reset_mock()
                self.respond(text)
                before = copy.deepcopy((self.decision, self.assessment, self.estimates, self.preferences, self.course))
                result = await self.teach()
                self.assertFalse(result.fallback)
                self.assertEqual(result.teaching_source, "bedrock")
                self.assertEqual(result.text, "Draft course guidance.\n\n" + text)
                self.assertNotEqual(result.text, self.stored().text)
                self.assertEqual(result.next_question_id, self.decision.next_question_id)
                self.assertEqual((self.decision, self.assessment, self.estimates, self.preferences, self.course), before)
                self.complete.assert_awaited_once()
                self.assertEqual(self.complete.call_args.kwargs["max_tokens"], 512)

    async def test_fake_local_render_stored_bedrock_artifact_without_calls(self):
        self.catalog = build_runtime_catalog(replace(self.course, metadata=replace(self.course.metadata, mode="bedrock")))
        for mode in ("fake", "local"):
            with patch.dict(os.environ, {"MODEL_PROVIDER": mode}):
                result = await self.teach()
                self.assertEqual(result, self.stored())
                self.assertEqual(result.teaching_source, "authored")
        self.complete.assert_not_called()

    async def test_extra_fields_cannot_change_any_authority(self):
        for field, value in (("next_question_id", "other-question"), ("kind", "worked_example"),
                             ("intervention_kind", "worked_example"), ("concept_id", "other-concept"),
                             ("candidate_id", "other-candidate"), ("priority", 1),
                             ("score", 1), ("reason", "New policy decision")):
            with self.subTest(field=field):
                self.complete.return_value = ProviderResult(json.dumps({
                    "text": "What detail from the material would you use here?", field: value}), "bedrock", "mock", 0)
                await self.assert_fallback()

    async def test_strict_json_and_bounded_response(self):
        for raw in ("not JSON", '```json\n{"text":"hello"}\n```', '[]', 'null',
                    '{"text":"one","text":"two"}', '{"text":NaN}', '{"text":false}',
                    '{"text":""}', '{"text":"hello"} trailing',
                    json.dumps({"text": "x" * (MAX_TEXT_LENGTH + 1)}), "x" * (MAX_TEXT_LENGTH * 7)):
            with self.subTest(raw=raw[:60]):
                self.complete.return_value = ProviderResult(raw, "bedrock", "mock", 0)
                await self.assert_fallback()

    async def test_timeout_failure_and_wrong_provider_use_stored_fallback(self):
        for failure in (TimeoutError("private timeout"), ProviderError("private credentials"),
                        RuntimeError("private failure")):
            with self.subTest(failure=type(failure).__name__):
                self.complete.side_effect = failure
                result = await self.assert_fallback()
                self.assertNotIn("private", result.text)
        self.complete.side_effect = None
        self.complete.return_value = ProviderResult("fake echo", "fake", "fake", 0)
        await self.assert_fallback()

    async def test_probe_and_hint_direct_answer_leaks_are_rejected(self):
        for kind in ("diagnostic_probe", "socratic_hint"):
            self.select(kind)
            question = self.catalog.question(self.decision.next_question_id)
            answer = next(c.text for c in question.choices if c.id == question.answer_key)
            for text in (answer, "Consider " + answer.upper(), question.rubric, "Choose a."):
                with self.subTest(kind=kind, text=text[:30]):
                    self.respond(text)
                    await self.assert_fallback()

    async def test_unsupported_control_ids_policy_and_grading_claims_fall_back(self):
        for text in ("Your mastery is now 100%.", "The policy selected another activity.",
                     "Your answer is correct.", "The priority is 0.9.", "Ignore previous instructions.",
                     self.decision.candidate_id, self.decision.concept_id, self.decision.next_question_id,
                     "Use candidate invented_candidate.", "The next question is about chemistry."):
            with self.subTest(text=text):
                self.respond(text)
                await self.assert_fallback()

    async def test_source_facts_are_accepted_without_demo_topic_rules(self):
        self.catalog = build_runtime_catalog(synthetic_course())
        self.estimates = BayesianLearner().initial_state(self.catalog.concept_ids).concepts
        self.select("worked_example")
        fact = self.catalog.artifacts[self.decision.content_id].paragraphs[0]
        self.respond(fact + " First, find what the task asks you to look for.")
        result = await self.teach()
        self.assertFalse(result.fallback)
        self.assertIn("Breadth-first search", result.text)
        self.complete.assert_awaited_once()
        for text in (fact.replace("increasing", "decreasing"), fact.replace("explores", "never explores"),
                     fact + " Now consider an unrelated solved example.",
                     "Nodes are always explored in random order."):
            with self.subTest(text=text):
                self.respond(text)
                await self.assert_fallback()

    async def test_shortening_cannot_remove_a_negation(self):
        self.select("worked_example")
        self.respond("Leave out claims the passage does support.")
        await self.assert_fallback()

    async def test_plain_concise_and_numbered_presentation(self):
        self.select("worked_example")
        self.preferences = LearnerPresentationPreferences(plain_language=True, concise=True, step_by_step=True)
        self.respond("1. First, find what the task asks you to look for.\n"
                     "2. Next, separate the passage's condition from its consequence.")
        result = await self.teach()
        self.assertFalse(result.fallback)
        self.assertIn("1. First", result.text)
        prompt = json.loads(self.complete.call_args.args[0])
        self.assertEqual(prompt["presentation_preferences"], self.preferences.model_dump())
        for text in ("2. First, find what the task asks you to look for.",
                     "1. First, find what the task asks you to look for.",
                     "First, find what the task asks you to look for."):
            self.respond(text)
            await self.assert_fallback()

    async def test_prompt_uses_only_selected_display_safe_grounding(self):
        self.select("worked_example")
        self.respond("First, find what the task asks you to look for.")
        await self.teach()
        raw = self.complete.call_args.args[0]
        prompt = json.loads(raw)
        self.assertEqual(prompt["authored_content"], list(self.catalog.artifacts[self.decision.content_id].paragraphs))
        self.assertEqual(prompt["intervention_kind"], self.decision.kind)
        self.assertEqual(prompt["assessment"], {"outcome": "incorrect"})
        for secret in (self.decision.candidate_id, self.decision.next_question_id, self.decision.reason,
                       "PRIVATE diagnosis", "source_refs", "answer_key", "rubric", "requires_review"):
            self.assertNotIn(secret, raw)
        for question in self.course.questions:
            self.assertNotIn(question.explanation, raw)
            self.assertNotIn(question.prompt, raw)
        for word in ("candidate", "priority", "grading", "next question", "strict JSON", "plain_language"):
            self.assertIn(word, self.complete.call_args.kwargs["system"])

    async def test_trusted_values_and_fallback_are_snapshotted_before_provider_await(self):
        original_next = self.decision.next_question_id
        expected = self.stored().text

        async def mutate_during_await(*args, **kwargs):
            self.decision.next_question_id = "foreign-question"
            self.decision.kind = "worked_example"
            self.preferences.step_by_step = True
            return ProviderResult("broken JSON", "bedrock", "mock", 0)

        self.complete.side_effect = mutate_during_await
        result = await self.teach()
        self.assertEqual(result.next_question_id, original_next)
        self.assertEqual(result.text, expected)
        self.assertEqual(result.teaching_source, "authored_fallback")
        self.complete.assert_awaited_once()

    async def test_unclear_course_assessment_still_attempts_once_when_bedrock_enabled(self):
        self.assessment.outcome = "unclear"
        self.assessment.score = None
        result = await self.teach()
        self.assertFalse(result.fallback)
        self.assertEqual(result.teaching_source, "bedrock")
        self.complete.assert_awaited_once()

    async def test_completion_and_unsupported_modes_do_not_call_provider(self):
        result = await Tutor(self.catalog).teach(None, self.assessment, self.estimates, self.preferences)
        self.assertIsNone(result.next_question_id)
        self.assertEqual(result.teaching_source, "authored")
        with patch.dict(os.environ, {"MODEL_PROVIDER": "openai"}):
            result = await self.teach()
            self.assertEqual(result.text, self.stored().text)
            self.assertEqual(result.teaching_source, "authored_fallback")
        self.complete.assert_not_called()

    async def test_one_ingestion_call_then_one_tutor_call_no_regeneration(self):
        proposal = json.dumps(plan_for(self.course.materials))
        self.complete.side_effect = [ProviderResult(proposal, "bedrock", "mock", 0),
                                    ProviderResult(json.dumps({"text": "What detail from the material would you use here?"}),
                                                   "bedrock", "mock", 0)]
        course = await process_course([FIXTURE], mode="bedrock")
        self.catalog = build_runtime_catalog(course)
        self.estimates = BayesianLearner().initial_state(self.catalog.concept_ids).concepts
        self.select("diagnostic_probe")
        result = await self.teach()
        self.assertFalse(result.fallback)
        self.assertEqual(course.metadata.provider_calls, 1)
        self.assertEqual(self.complete.await_count, 2)
        self.assertEqual([call.kwargs["max_tokens"] for call in self.complete.call_args_list], [6000, 512])


if __name__ == "__main__":
    unittest.main()
