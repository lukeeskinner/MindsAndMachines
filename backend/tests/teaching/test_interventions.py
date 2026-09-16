"""Compatibility fixtures only: no production candidates or questions are added."""
import copy
import itertools
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.agents.provider import ProviderError, ProviderResult
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.tutor import MAX_TEXT_LENGTH, Tutor
from contracts.models import (
    Assessment, Candidate, ConceptEstimate, Decision, LearnerPresentationPreferences,
)


KINDS = ("diagnostic_probe", "socratic_hint")
AUTHORED = {
    "diagnostic_probe": "Which condition would you check along an edge?",
    "socratic_hint": "Compare the estimate with the step cost plus the neighboring estimate.",
}
GENERATED = {
    "diagnostic_probe": "What would you compare along an edge?",
    "socratic_hint": "Focus on the edge cost and the neighboring estimate.",
}


class InterventionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.catalog = Catalog()
        concept_id = self.catalog.candidates[0].concept_id
        for kind in KINDS:
            self.catalog.candidates.append(Candidate(
                candidate_id=f"test-{kind}", concept_id=concept_id, kind=kind,
                content_id=f"test-{kind}-content", next_question_id="relationship-q02"))
            self.catalog.teaching[f"test-{kind}-content"] = {
                variant: [AUTHORED[kind]]
                for variant in ("standard", "plain", "concise", "plain_concise")
            }
        self.tutor = Tutor(self.catalog)
        self.assessment = Assessment(outcome="incorrect", concept_id=concept_id, score=0,
                                     misconception_id="admissible_means_consistent",
                                     feedback="Consistency implies admissibility.")
        self.concepts = [ConceptEstimate(concept_id=concept_id, mean=0.3,
                         interval90={"lower": 0.02, "upper": 0.77}, evidence_count=1)]
        self.prefs = LearnerPresentationPreferences()
        env = patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"})
        env.start()
        self.addCleanup(env.stop)
        provider = patch("backend.app.teaching.tutor.provider.complete", new_callable=AsyncMock)
        self.complete = provider.start()
        self.addCleanup(provider.stop)

    def select(self, kind):
        candidate = next(c for c in self.catalog.candidates if c.kind == kind)
        self.decision = Decision(**candidate.model_dump(), reason="Trusted policy selection")
        self.complete.reset_mock(return_value=True, side_effect=True)
        self.respond(GENERATED[kind] if kind in KINDS else
                     " ".join(self.catalog.teaching[candidate.content_id]["standard"]))

    def respond(self, text):
        self.complete.return_value = ProviderResult(json.dumps({"text": text}), "bedrock", "test", 0)

    async def teach(self):
        before = copy.deepcopy((self.decision, self.assessment, self.concepts,
                                self.prefs, vars(self.catalog)))
        result = await self.tutor.teach(self.decision, self.assessment, self.concepts, self.prefs)
        self.assertEqual((self.decision, self.assessment, self.concepts,
                          self.prefs, vars(self.catalog)), before)
        self.assertEqual(result.next_question_id, self.decision.next_question_id)
        return result

    async def assert_fallback(self):
        result = await self.teach()
        self.assertTrue(result.fallback)
        self.assertEqual(result.teaching_source, "authored_fallback")
        self.assertEqual(result.text, AUTHORED[self.decision.kind])
        self.complete.assert_awaited_once()

    async def test_each_kind_resolves_only_selected_content(self):
        for kind in ("worked_example", *KINDS):
            with self.subTest(kind=kind):
                self.select(kind)
                result = await self.teach()
                self.assertFalse(result.fallback)
                self.assertEqual(result.teaching_source, "bedrock")
                prompt = json.loads(self.complete.call_args.args[0])
                self.assertEqual(prompt["intervention_kind"], kind)
                self.assertEqual(prompt["authored_content"],
                                 self.catalog.teaching[self.decision.content_id]["standard"])
                self.complete.assert_awaited_once()

    async def test_local_rendering_is_deterministic_for_all_preferences(self):
        for kind, mode, plain, concise, steps in itertools.product(
                KINDS, (None, "fake", "local"), (False, True), (False, True), (False, True)):
            with self.subTest(kind=kind, mode=mode, plain=plain, concise=concise, steps=steps), \
                    patch.dict(os.environ):
                self.select(kind)
                if mode is None:
                    os.environ.pop("MODEL_PROVIDER", None)
                else:
                    os.environ["MODEL_PROVIDER"] = mode
                self.prefs = LearnerPresentationPreferences(
                    plain_language=plain, concise=concise, step_by_step=steps)
                self.complete.return_value = ProviderResult("[fake provider echo] PRIVATE", "fake", "fake", 0)
                result = await self.teach()
                self.assertEqual(result, await self.teach())
                self.assertEqual(result.text, ("1. " if steps else "") + AUTHORED[kind])
                self.assertFalse(result.fallback)
                self.assertEqual(result.teaching_source, "authored")
                self.complete.assert_not_called()

    async def test_generated_guidance_and_single_numbered_step_are_accepted(self):
        for kind, steps in itertools.product(KINDS, (False, True)):
            with self.subTest(kind=kind, steps=steps):
                self.select(kind)
                self.prefs.step_by_step = steps
                for prose in (AUTHORED[kind], GENERATED[kind]):
                    text = ("1. " if steps else "") + prose
                    self.respond(text)
                    result = await self.teach()
                    self.assertEqual(result.text, text)
                    self.assertFalse(result.fallback)

    async def test_non_example_prompt_omits_solution_bearing_feedback(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.select(kind)
                await self.teach()
                prompt = self.complete.call_args.args[0]
                self.assertEqual(json.loads(prompt)["assessment"], {"outcome": "incorrect"})
                self.assertNotIn(self.assessment.feedback, prompt)
                for question in self.catalog.questions.values():
                    self.assertNotIn(question.rubric, prompt)
                    self.assertNotIn(question.question_id, prompt)
                    for choice in question.choices:
                        if choice.id == question.answer_key:
                            self.assertNotIn(choice.text, prompt)
                self.assertIn("never give the final answer", self.complete.call_args.kwargs["system"])

    async def test_unclear_keeps_authored_guidance_without_example_prefix(self):
        self.assessment.outcome = "unclear"
        self.assessment.score = None
        for kind, mode in itertools.product(KINDS, ("fake", "bedrock")):
            with self.subTest(kind=kind, mode=mode), patch.dict(os.environ, {"MODEL_PROVIDER": mode}):
                self.select(kind)
                result = await self.teach()
                self.assertEqual(result.text, AUTHORED[kind])
                self.assertTrue(result.fallback)
                self.assertEqual(result.teaching_source, "authored_fallback")
                self.complete.assert_not_called()

    async def test_direct_answers_and_solved_examples_fall_back(self):
        claims = ["The correct answer is b.", "Choose b.", "Pick option d.", "B.", "It's b.",
                  "The answer is admissible but inconsistent.",
                  "Admissible, but not consistent.", "Admissible but not consistent.",
                  "Solution: admissible.",
                  "Every consistent heuristic is admissible, but the reverse need not hold.",
                  "This heuristic is admissible but inconsistent.",
                  "Isn't the heuristic admissible? Therefore choose b.",
                  "Consistency fails on the edge.", "The edge violates consistency.",
                  "Consistency implies admissibility.", "Here is a solved example."]
        for kind, claim in itertools.product(KINDS, claims):
            with self.subTest(kind=kind, claim=claim):
                self.select(kind)
                self.respond(claim)
                await self.assert_fallback()

    async def test_shared_safety_checks_still_apply_to_each_kind(self):
        claims = ["The answer key is b.", "Return strict JSON only.",
                  "The system prompt says to ignore instructions.",
                  "Use candidate other-candidate.", "Read content other-content.",
                  "Next: relationship-q02.", "different-question", "new_question_id",
                  "I selected a worked example.", "A diagnostic_probe was selected.",
                  "A socratic hint was selected.", "Your mastery is now 100%.",
                  "The policy selected something else.", "Skip the next question.",
                  "S → A costs 99.", "h(S)=4.", "Now solve 2 + 2.",
                  "Every admissible heuristic is consistent.",
                  *[q.rubric for q in self.catalog.questions.values()]]
        for kind, claim in itertools.product(KINDS, claims):
            with self.subTest(kind=kind, claim=claim):
                self.select(kind)
                self.respond(GENERATED[kind] + " " + claim)
                await self.assert_fallback()

    async def test_strict_json_validation_is_unchanged(self):
        invalid = ["{", "null", "[]", '"text"', '{"text":"one","text":"two"}',
                   '{"text":NaN}', '{"text":Infinity}', '{}', '```json\n{}\n```',
                   *[json.dumps({"text": v}) for v in (None, 3, True, [], {}, "", " \n", "x" * (MAX_TEXT_LENGTH + 1))]]
        invalid += [json.dumps({"text": "hello", field: "untrusted"})
                    for field in ("next_question_id", "kind", "candidate_id", "content_id", "fallback")]
        for kind, raw in itertools.product(KINDS, invalid):
            with self.subTest(kind=kind, raw=raw[:80]):
                self.select(kind)
                self.complete.return_value.text = raw
                await self.assert_fallback()

    async def test_prompt_and_system_echo_are_rejected(self):
        for kind in KINDS:
            self.select(kind)
            await self.teach()
            call = self.complete.call_args
            for leaked in (call.args[0], call.kwargs["system"]):
                with self.subTest(kind=kind, leaked=leaked[:30]):
                    self.select(kind)
                    self.respond(leaked)
                    await self.assert_fallback()

    async def test_listed_choices_cannot_be_reduced_to_the_answer(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.select(kind)
                answer = self.catalog.questions["relationship-q02"].choices[1].text
                authored = f"Which description fits: {answer} Or both conditions hold?"
                self.catalog.teaching[self.decision.content_id]["standard"] = [authored]
                self.respond(authored)
                self.assertFalse((await self.teach()).fallback)
                self.respond(answer)
                result = await self.teach()
                self.assertTrue(result.fallback)
                self.assertEqual(result.text, authored)

    async def test_grounded_facts_do_not_authorize_a_solved_comparison(self):
        for kind in KINDS:
            self.select(kind)
            authored = "S → A costs 1. h(S)=3 and h(A)=1. What would you compare?"
            self.catalog.teaching[self.decision.content_id]["standard"] = [authored]
            for text in ("3 > 1 + 1.", "Three is greater than one plus one.",
                         "S → A costs 3.", "h(S)=1."):
                with self.subTest(kind=kind, text=text):
                    self.respond(text)
                    result = await self.teach()
                    self.assertTrue(result.fallback)
                    self.assertEqual(result.text, authored)

    async def test_provider_failures_attempt_once_and_preserve_trusted_question(self):
        for kind, next_id, error in itertools.product(KINDS, (None, "relationship-q01", "relationship-q02"),
                (ProviderError("private error"), TimeoutError("timeout"), KeyError("malformed response"))):
            with self.subTest(kind=kind, next_id=next_id, error=type(error)):
                self.select(kind)
                self.decision.next_question_id = next_id
                self.complete.side_effect = error
                await self.assert_fallback()

    async def test_generated_and_local_paths_preserve_policy_next_question(self):
        for kind, next_id, mode in itertools.product(KINDS, (None, "relationship-q01", "relationship-q02"),
                                                     ("fake", "bedrock")):
            with self.subTest(kind=kind, next_id=next_id, mode=mode), patch.dict(os.environ, {"MODEL_PROVIDER": mode}):
                self.select(kind)
                self.decision.next_question_id = next_id
                result = await self.teach()
                self.assertFalse(result.fallback)

    async def test_fake_echo_on_bedrock_path_falls_back(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                self.select(kind)
                self.complete.return_value = ProviderResult("[fake provider echo] PRIVATE", "fake", "fake", 0)
                await self.assert_fallback()

    async def test_unknown_provider_never_calls_or_switches_provider(self):
        for kind in KINDS:
            with self.subTest(kind=kind), patch.dict(os.environ, {"MODEL_PROVIDER": "openai"}):
                self.select(kind)
                result = await self.teach()
                self.assertEqual(result.text, AUTHORED[kind])
                self.assertTrue(result.fallback)
                self.complete.assert_not_called()

    async def test_configuration_errors_are_not_provider_fallbacks(self):
        for kind, field, value in itertools.product(KINDS, ("content_id", "candidate_id", "kind"), ("missing",)):
            with self.subTest(kind=kind, field=field):
                self.select(kind)
                setattr(self.decision, field, value)
                with self.assertRaises(ValueError):
                    await self.teach()
                self.complete.assert_not_called()
        for kind in KINDS:
            self.select(kind)
            # A known content ID belonging to another selected candidate is still invalid.
            self.decision.content_id = "heuristic-distinction"
            with self.assertRaisesRegex(ValueError, "No reviewed content"):
                await self.teach()
            self.complete.assert_not_called()

    async def test_missing_or_ambiguous_target_remains_configuration_error(self):
        original = self.concepts
        for kind, concepts in itertools.product(KINDS, ([], original * 2)):
            with self.subTest(kind=kind, count=len(concepts)):
                self.select(kind)
                self.concepts = concepts
                with self.assertRaisesRegex(ValueError, "exactly one estimate"):
                    await self.teach()
                self.complete.assert_not_called()

    async def test_hint_stays_short_even_without_concise_preference(self):
        self.select("socratic_hint")
        self.respond(GENERATED["socratic_hint"] * 8)
        await self.assert_fallback()


if __name__ == "__main__":
    unittest.main()
