import copy
import json
import os
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.agents.provider import ProviderError, ProviderResult
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.fake import FakeTutor
from backend.app.teaching.tutor import MAX_TEXT_LENGTH, Tutor
from contracts.models import Assessment, ConceptEstimate, Decision, LearnerPresentationPreferences


class TutorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.tutor = Tutor(self.catalog)
        self.decision = Decision(**self.catalog.candidates[0].model_dump(), reason="Policy selected this example")
        self.assessment = Assessment(outcome="incorrect", concept_id=self.decision.concept_id,
                                     score=0, misconception_id="admissible_means_consistent",
                                     feedback="An admissible heuristic need not be consistent.")
        self.concepts = [ConceptEstimate(concept_id=concept_id, mean=0.3 if i == 5 else 0.5,
                        interval90={"lower": 0.02, "upper": 0.77}, evidence_count=1)
                         for i, concept_id in enumerate(self.catalog.concept_ids)]
        self.prefs = LearnerPresentationPreferences()
        self.env = patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.provider_patch = patch("backend.app.teaching.tutor.provider.complete", new_callable=AsyncMock)
        self.complete = self.provider_patch.start()
        self.addCleanup(self.provider_patch.stop)
        # A valid composition with new paragraph breaks and no optional invitation.
        self.generated = " ".join(self.catalog.teaching["heuristic-distinction"]["standard"])
        self.generated = self.generated.removesuffix(" Try checking both conditions on the fresh graph.")
        self.respond(self.generated)

    def respond(self, text):
        self.complete.return_value = ProviderResult(json.dumps({"text": text}), "bedrock", "test-model", 1.0)

    async def teach(self):
        return await self.tutor.teach(self.decision, self.assessment, self.concepts, self.prefs)

    async def reviewed(self):
        return await FakeTutor(self.catalog).teach(self.decision, self.assessment, self.concepts, self.prefs)

    async def assert_fallback(self):
        result = await self.teach()
        self.assertTrue(result.fallback)
        self.assertEqual(result.teaching_source, "authored_fallback")
        self.assertEqual(result.text, (await self.reviewed()).text)
        self.assertEqual(result.next_question_id, self.decision.next_question_id)
        return result

    def prompt(self):
        return json.loads(self.complete.call_args.args[0])

    async def test_completion_without_provider_even_when_unclear(self):
        self.decision = None
        for outcome in ["correct", "incorrect", "unclear"]:
            with self.subTest(outcome=outcome):
                self.assessment.outcome = outcome
                result = await self.teach()
                self.assertEqual(result.text, "This demo is complete. Start a new session to replay it.")
                self.assertIsNone(result.next_question_id)
                self.assertFalse(result.fallback)
        self.complete.assert_not_called()

    async def test_fake_local_and_default_never_call_or_display_echo(self):
        for mode in [None, "fake", "local"]:
            with self.subTest(mode=mode), patch.dict(os.environ):
                if mode is None:
                    os.environ.pop("MODEL_PROVIDER", None)
                else:
                    os.environ["MODEL_PROVIDER"] = mode
                self.complete.return_value = ProviderResult("[fake provider echo] PRIVATE PROMPT", "fake", "fake", 0)
                for outcome in ["correct", "incorrect"]:
                    self.assessment.outcome = outcome
                    self.assertEqual(await self.teach(), await self.reviewed())
                    self.assertFalse((await self.teach()).fallback)
        self.complete.assert_not_called()

    async def test_valid_bedrock_generation(self):
        result = await self.teach()
        self.complete.assert_awaited_once()
        self.assertEqual(result.text, self.generated)
        self.assertFalse(result.fallback)
        self.assertEqual(result.next_question_id, "relationship-q02")
        self.assertEqual(result.teaching_source, "bedrock")
        self.assertEqual(self.complete.call_args.kwargs["max_tokens"], 512)

    async def assert_generated(self, text):
        self.respond(text)
        result = await self.teach()
        self.assertEqual(result.text, text)
        self.assertFalse(result.fallback)
        self.assertEqual(result.next_question_id, self.decision.next_question_id)
        return result

    async def test_exact_authored_output_is_accepted(self):
        await self.assert_generated((await self.reviewed()).text)

    async def test_grounded_paraphrase_is_accepted(self):
        await self.assert_generated(
            "Admissibility puts a ceiling on the estimate of the remaining cost; "
            "consistency checks how that estimate changes along an edge.\n\n"
            "Consider S to A costing one and A to G costing two. "
            "Use h(S)=3, h(A)=1 and h(G)=0. These estimates do not overestimate "
            "the remaining costs, yet the first edge fails consistency because "
            "1 + 1 < 3. The heuristic is admissible but inconsistent.\n\n"
            "With a zero estimate at the goal, consistency implies admissibility; "
            "the converse need not hold.")

    async def test_authored_content_plus_assessment_feedback_is_accepted(self):
        await self.assert_generated(self.generated + " " + self.assessment.feedback)

    async def test_minor_invitation_rewording_is_accepted(self):
        await self.assert_generated((await self.reviewed()).text.replace(
            "Try checking both conditions", "Check both conditions"))

    async def test_reported_nova_wording_is_accepted(self):
        # Regression for the described live output, not a claimed full captured response.
        self.assessment.feedback = (
            "The distinction to revisit: an admissible heuristic need not be consistent.")
        explanation = " ".join(self.catalog.teaching["heuristic-distinction"]["standard"][:2])
        await self.assert_generated(explanation + " " + self.assessment.feedback
                                    + " Check both conditions on the fresh graph.")
        self.complete.assert_awaited_once()

    async def test_reported_nova_new_graph_ending_is_accepted(self):
        # Exact complete Nova response supplied from the user's live diagnostic.
        await self.assert_generated(
            "An admissible heuristic does not have to be consistent. Let's revisit the definitions: "
            "admissibility means that the heuristic's estimate never exceeds the optimal path cost "
            "to the goal, while consistency means that the heuristic's estimate for a node is not "
            "greater than the cost of reaching any neighboring node plus the estimate for that "
            "neighbor. Despite the confusion, admissibility alone does not ensure consistency. "
            "For instance, using h(S) = 3, h(A) = 1, and h(G) = 0 for nodes S, A, and G respectively, "
            "with paths S → A costing 1 and A → G costing 2, we find that all heuristics are "
            "admissible. However, the edge S → A is inconsistent because 3 > 1 + 1. "
            "It's crucial to verify both admissibility and consistency "
            "when evaluating a heuristic on a new graph.")

    async def test_generic_new_graph_reference_is_accepted(self):
        await self.assert_generated(self.generated + " Check this on a new graph.")

    async def test_generic_another_graph_reference_is_accepted(self):
        await self.assert_generated(self.generated + " Apply the same reasoning to another graph.")

    async def test_exact_nova_response_with_verbal_values_is_accepted(self):
        await self.assert_generated(
            "An admissible heuristic does not always mean the heuristic is consistent. For instance,\n"
            "let's consider the costs between S → A and A → G. If S → A has a cost of 1 and A → G\n"
            "has a cost of 2, we can set h(S) to 3, h(A) to 1, and h(G) to 0. In this case, all\n"
            "estimates are admissible, but the S → A edge is inconsistent because 3 is greater than\n"
            "1 + 1. It is crucial to check both admissibility and consistency conditions on the graph.\n"
            "Remember, with h(goal) set to 0, consistency implies admissibility, but admissibility alone\n"
            "does not guarantee consistency.")

    async def test_verbal_comparison_is_accepted_without_other_values(self):
        await self.assert_generated("3 is greater than 1 + 1, so the edge violates consistency.")

    async def test_spelled_out_comparison_is_accepted(self):
        await self.assert_generated(
            "Three is greater than one plus one, so this edge violates consistency.")

    async def test_partial_example_values_are_accepted(self):
        for text in ["S → A costs 1. This edge violates consistency in the authored example.",
                     "With h(S)=3 and h(A)=1, the estimate drops too far on the first edge.",
                     "The estimates are admissible, but consistency fails along the first edge."]:
            with self.subTest(text=text):
                await self.assert_generated(text)

    async def test_reordered_partial_facts_are_accepted(self):
        await self.assert_generated(
            "The heuristic is admissible but inconsistent.\n\n"
            "h(G) is set to 0, while h(S) is 3.\n\n"
            "A → G has a cost of 2; S → A costs 1.")

    async def test_explicit_conflicts_rejected_without_complete_example(self):
        for text in ["S → A costs 4.", "A → G costs 7.", "h(S)=2.",
                     "h(A)=5.", "h(G)=1.", "3 < 1 + 1."]:
            with self.subTest(text=text):
                self.respond(text)
                await self.assert_fallback()

    async def test_verbal_assignments_with_conflicting_values_are_rejected(self):
        # Values 1/2/3 already occur in the source: the bound variable matters.
        for text in ["S → A has a cost of 2.", "A → G has a cost of 1.",
                     "Set h(S) to 2.", "Set h(A) to 3.", "h(G) is set to 1."]:
            with self.subTest(text=text):
                self.respond(self.generated + " " + text)
                await self.assert_fallback()

    async def test_false_spoken_comparisons_are_rejected(self):
        for text in ["3 is less than 1 + 1.", "Three is less than one plus one.",
                     "Three is equal to one plus one.", "Three is greater than three plus one."]:
            with self.subTest(text=text):
                self.respond(self.generated + " " + text)
                await self.assert_fallback()

    async def test_different_selected_example_nodes_are_rejected(self):
        for text in ["The selected example uses nodes X and Y.",
                     "The selected graph contains vertices S, A, and X.",
                     "The example uses node X.", "The example has X → Y costing 1."]:
            with self.subTest(text=text):
                self.respond(self.generated + " " + text)
                await self.assert_fallback()

    async def test_new_graph_with_different_nodes_is_rejected(self):
        for extra in ["On a new graph, X → Y costs 1.",
                      "Consider another graph with nodes X and Y.",
                      "Consider X → Y costing 1."]:
            with self.subTest(extra=extra):
                self.respond(self.generated + " " + extra)
                await self.assert_fallback()

    async def test_new_graph_with_different_edge_cost_is_rejected(self):
        for extra in ["On a new graph, S → A costs 2.", "S → A costs 2."]:
            with self.subTest(extra=extra):
                self.respond(self.generated + " " + extra)
                await self.assert_fallback()

    async def test_new_graph_with_different_heuristic_is_rejected(self):
        for extra in ["On another graph, h(S)=2.", "h(S)=2."]:
            with self.subTest(extra=extra):
                self.respond(self.generated + " " + extra)
                await self.assert_fallback()

    async def test_new_graph_does_not_permit_a_different_exercise(self):
        for extra in ["On a new graph, solve 2 + 2.",
                      "Find the cheapest route on another graph.",
                      "Here is another exercise: solve 2 + 2."]:
            with self.subTest(extra=extra):
                self.respond(self.generated + " " + extra)
                await self.assert_fallback()

    async def test_generic_graph_reference_does_not_permit_a_different_concept(self):
        self.respond(self.generated + " Apply breadth-first search on a new graph.")
        await self.assert_fallback()

    async def test_new_graph_does_not_permit_new_numerical_comparisons(self):
        for extra in ["On another graph, 2 > 1 + 0.", "On a new graph, 4 > 1 + 1.",
                      "For this example, 3 < 1 + 1."]:
            with self.subTest(extra=extra):
                self.respond(self.generated + " " + extra)
                await self.assert_fallback()

    async def test_reordered_paragraphs_are_accepted(self):
        paragraphs = self.catalog.teaching["heuristic-distinction"]["standard"]
        await self.assert_generated("\n\n".join([paragraphs[2], paragraphs[1], paragraphs[0]]))

    async def test_shortened_example_is_accepted(self):
        await self.assert_generated(
            "S → A costs 1 and A → G costs 2. With estimates (3,1,0), "
            "the heuristic is admissible but inconsistent: 3 > 1 + 1 on S → A.")

    async def test_plain_language_paraphrase_with_all_preferences(self):
        self.prefs = LearnerPresentationPreferences(plain_language=True, step_by_step=True, concise=True)
        await self.assert_generated(
            "1. Take S to A costing one and A to G costing two.\n"
            "2. Guesses of three at S, one at A and zero at G never overestimate.\n"
            "3. The first guess drops by two on a step costing one: admissible, but not consistent.")

    async def test_worked_example_remains_authoritative(self):
        before = self.decision.model_dump()
        await self.teach()
        self.assertEqual(self.prompt()["intervention_kind"], "worked_example")
        self.assertEqual(self.prompt()["authored_content"], self.catalog.teaching["heuristic-distinction"]["standard"])
        self.assertEqual(self.decision.model_dump(), before)

    async def test_correct_answer_prompt(self):
        self.assessment = self.assessment.model_copy(update={"outcome": "correct", "score": 1,
            "misconception_id": None, "feedback": "The distinction is correct."})
        await self.teach()
        self.assertEqual(self.prompt()["assessment"], {"outcome": "correct", "feedback": "The distinction is correct."})

    async def test_incorrect_answer_prompt_with_misconception(self):
        await self.teach()
        self.assertEqual(self.prompt()["assessment"], {"outcome": "incorrect",
            "feedback": self.assessment.feedback, "misconception_id": "admissible_means_consistent"})

    async def test_only_target_estimate_is_included(self):
        await self.teach()
        self.assertEqual(self.prompt()["target_estimate"], {"concept_id": self.decision.concept_id,
            "mean": 0.3, "interval90": {"lower": 0.02, "upper": 0.77}})
        self.assertEqual(set(self.prompt()), {"intervention_kind", "authored_content", "assessment",
                                             "target_estimate", "presentation_preferences"})
        for concept_id in ["bfs", "ucs", "astar"]:
            self.assertNotIn(concept_id, self.complete.call_args.args[0])

    async def test_prompt_excludes_private_question_data(self):
        # Private rubrics may be checked locally, but never enter the provider prompt.
        with patch.object(self.catalog, "question", side_effect=AssertionError("Private lookup")):
            await self.teach()
        prompt = self.complete.call_args.args[0]
        for question in self.catalog.questions.values():
            self.assertNotIn(question.rubric, prompt)
            self.assertNotIn(question.prompt, prompt)
            self.assertNotIn(question.question_id, prompt)
        for private_field in ["answer_key", "rubric", "choices", "next_question_id", "session_id", "AWS_REGION"]:
            self.assertNotIn(private_field, prompt)
        self.assertNotIn("4 > 1+1", prompt)
        self.assertNotIn("h(S)=4", prompt)

    async def test_system_instruction_establishes_trust_boundary(self):
        await self.teach()
        system = self.complete.call_args.kwargs["system"]
        for instruction in ["selected", "authored content", "another activity", "another question",
                            "answer keys", "rubrics", "mastery", "preferences", "strict JSON"]:
            self.assertIn(instruction, system)
        self.assertIn("paraphrase, shorten, reorganize", system)
        self.assertNotIn("do not add or paraphrase sentences", system)

    async def check_preferences(self, variant, **preferences):
        self.prefs = LearnerPresentationPreferences(**preferences)
        expected = await self.reviewed()
        self.respond(expected.text)
        result = await self.teach()
        self.assertEqual(result.text, expected.text)
        self.assertFalse(result.fallback)
        self.assertEqual(self.prompt()["presentation_preferences"], self.prefs.model_dump())
        self.assertEqual(self.prompt()["authored_content"], self.catalog.teaching["heuristic-distinction"][variant])
        self.complete.side_effect = ProviderError("private failure")
        await self.assert_fallback()
        with patch.dict(os.environ, {"MODEL_PROVIDER": "fake"}):
            self.assertEqual(await self.teach(), expected)

    async def test_plain_language(self):
        await self.check_preferences("plain", plain_language=True)

    async def test_concise(self):
        await self.check_preferences("concise", concise=True)

    async def test_step_by_step(self):
        await self.check_preferences("standard", step_by_step=True)

    async def test_all_preferences(self):
        await self.check_preferences("plain_concise", plain_language=True, concise=True, step_by_step=True)

    async def test_unfulfilled_presentation_preferences_fall_back(self):
        for prefs in [{"plain_language": True}, {"concise": True}, {"step_by_step": True}]:
            with self.subTest(preferences=prefs):
                self.prefs = LearnerPresentationPreferences(**prefs)
                await self.assert_fallback()

    async def test_unclear_uses_authored_fallback_without_provider(self):
        self.assessment = self.assessment.model_copy(update={"outcome": "unclear", "score": None})
        for mode in ["fake", "bedrock"]:
            with patch.dict(os.environ, {"MODEL_PROVIDER": mode}):
                result = await self.assert_fallback()
                self.assertTrue(result.text.startswith("Let's try another example.\n\n"))
        self.complete.assert_not_called()

    async def test_provider_error(self):
        self.complete.side_effect = ProviderError("SECRET credentials and prompt")
        result = await self.assert_fallback()
        self.assertNotIn("SECRET", result.text)
        self.complete.assert_awaited_once()

    async def test_unexpected_provider_exception(self):
        self.complete.side_effect = KeyError("Malformed Bedrock response")
        await self.assert_fallback()
        self.complete.assert_awaited_once()

    async def test_provider_timeout_exception(self):
        self.complete.side_effect = TimeoutError("SDK timeout")
        await self.assert_fallback()
        self.complete.assert_awaited_once()

    async def test_malformed_json(self):
        for raw in ["{", '```json\n{"text":"hello"}\n```', '{"text":"hello"} trailing']:
            with self.subTest(raw=raw):
                self.complete.return_value.text = raw
                await self.assert_fallback()

    async def test_non_object_json(self):
        for raw in ["null", "[]", '"hello"', "1", "true"]:
            with self.subTest(raw=raw):
                self.complete.return_value.text = raw
                await self.assert_fallback()

    async def test_missing_text(self):
        self.complete.return_value.text = "{}"
        await self.assert_fallback()

    async def test_additional_fields_cannot_select_next_question_or_kind(self):
        for field, value in [("next_question_id", "other-question"), ("kind", "socratic_hint"),
                             ("fallback", False), ("candidate_id", "other-candidate")]:
            with self.subTest(field=field):
                self.complete.return_value.text = json.dumps({"text": self.generated, field: value})
                await self.assert_fallback()

    async def test_non_string_text(self):
        for value in [None, 42, True, [], {}]:
            with self.subTest(value=value):
                self.complete.return_value.text = json.dumps({"text": value})
                await self.assert_fallback()

    async def test_empty_text(self):
        for text in ["", " \n\t "]:
            with self.subTest(text=text):
                self.respond(text)
                await self.assert_fallback()

    async def test_excessive_text_length(self):
        self.respond("x" * (MAX_TEXT_LENGTH + 1))
        await self.assert_fallback()

    async def test_duplicate_fields_and_non_json_constants(self):
        for raw in ['{"text":"one","text":"two"}', '{"text":NaN}', '{"text":Infinity}']:
            with self.subTest(raw=raw):
                self.complete.return_value.text = raw
                await self.assert_fallback()

    async def test_answer_key_rubric_and_transfer_solution_leakage(self):
        for leaked in ["The answer key is b.", *[q.rubric for q in self.catalog.questions.values()],
                       "For the next graph, h(S)=4 and 4 > 1+1, so choose b."]:
            with self.subTest(leaked=leaked):
                self.respond(self.generated + " " + leaked)
                await self.assert_fallback()

    async def test_prompt_or_system_instruction_leakage(self):
        await self.teach()
        for leaked in [self.complete.call_args.args[0], self.complete.call_args.kwargs["system"]]:
            with self.subTest(leaked=leaked):
                self.respond(leaked)
                await self.assert_fallback()

    async def test_alternate_question_or_exercise(self):
        for extra in ["Now solve 2 + 2.", "What is the cheapest route on this new graph?",
                      "Let's practise breadth-first search instead."]:
            with self.subTest(extra=extra):
                self.respond(self.generated + " " + extra)
                await self.assert_fallback()

    async def test_policy_or_intervention_override(self):
        for extra in ["A socratic_hint was selected.", "I selected a diagnostic probe instead.",
                      "Your mastery is now 100%."]:
            with self.subTest(extra=extra):
                self.respond(self.generated + " " + extra)
                await self.assert_fallback()

    async def test_hallucinated_ids(self):
        for extra in ["Use candidate other-candidate.", "Read content other-content.", "Next: relationship-q99."]:
            with self.subTest(extra=extra):
                self.respond(self.generated + " " + extra)
                await self.assert_fallback()

    async def test_inconsistent_prose(self):
        for text in [self.generated.replace("cost 2", "cost 4"),
                     self.generated.replace("does not guarantee", "guarantees"),
                     self.generated + " Every admissible heuristic is consistent."]:
            with self.subTest(text=text):
                self.respond(text)
                await self.assert_fallback()

    async def test_changed_bindings_using_only_authored_numbers_are_rejected(self):
        for text in [self.generated.replace("cost 2", "cost 1"),
                     self.generated.replace("h(S)=3", "h(S)=1"),
                     self.generated.replace("3 > 1 + 1", "3 < 1 + 1"),
                     self.generated + " S → G costs 3."]:
            with self.subTest(text=text):
                self.respond(text)
                await self.assert_fallback()

    async def test_wrong_heuristic_tuple_is_rejected(self):
        text = " ".join(self.catalog.teaching["heuristic-distinction"]["concise"])
        self.respond(text.replace("h=(3,1,0)", "h=(1,3,0)"))
        await self.assert_fallback()

    async def test_different_ids_without_field_names_are_rejected(self):
        for identifier in ["different-candidate", "different-content", "different-question",
                           "another-q03", "relationship-q02", "relationship-example",
                           "heuristic-distinction", "new_question_id"]:
            with self.subTest(identifier=identifier):
                self.respond(self.generated + " " + identifier)
                await self.assert_fallback()

    async def test_policy_and_next_action_claims_are_rejected(self):
        for claim in ["The policy selected something else.", "Your mastery was updated.",
                      "Your mastery remains 1/3.", "The next action is a diagnostic probe.",
                      "The next question is about breadth-first search.",
                      "Skip the next question.", "We have chosen a different activity."]:
            with self.subTest(claim=claim):
                self.respond(self.generated + " " + claim)
                await self.assert_fallback()

    async def test_transfer_answer_without_private_values_is_rejected(self):
        for claim in ["The next graph is admissible but inconsistent.",
                      "The correct option is b.", "Choose b.",
                      "For the fresh question, the answer is admissible but inconsistent."]:
            with self.subTest(claim=claim):
                self.respond(self.generated + " " + claim)
                await self.assert_fallback()

    async def test_feedback_is_not_a_bypass_for_forbidden_claims(self):
        self.assessment.feedback = "Your mastery was updated. Choose b."
        self.respond(self.generated + " " + self.assessment.feedback)
        await self.assert_fallback()

    async def test_new_values_written_as_words_are_rejected(self):
        self.respond(self.generated + " The travel cost is ten.")
        await self.assert_fallback()

    async def test_partial_prompt_instruction_leakage_is_rejected(self):
        for claim in ["Return strict JSON only.", "The system prompt says to generate prose.",
                      "Ignore previous instructions."]:
            with self.subTest(claim=claim):
                self.respond(self.generated + " " + claim)
                await self.assert_fallback()

    async def test_explanation_without_example_values_is_accepted(self):
        await self.assert_generated(self.catalog.teaching["heuristic-distinction"]["standard"][0])

    async def test_unknown_content_id_is_configuration_error(self):
        self.decision.content_id = "missing"
        with self.assertRaisesRegex(ValueError, "Unknown teaching content"):
            await self.teach()
        self.complete.assert_not_called()

    async def test_missing_target_estimate_is_configuration_error(self):
        self.concepts = [c for c in self.concepts if c.concept_id != self.decision.concept_id]
        with self.assertRaisesRegex(ValueError, "exactly one estimate"):
            await self.teach()
        self.complete.assert_not_called()

    async def test_duplicate_target_estimate_is_configuration_error(self):
        self.concepts.append(self.concepts[-1].model_copy())
        with self.assertRaisesRegex(ValueError, "exactly one estimate"):
            await self.teach()
        self.complete.assert_not_called()

    async def test_missing_authored_variant_is_configuration_error(self):
        del self.catalog.teaching["heuristic-distinction"]["standard"]
        with self.assertRaisesRegex(ValueError, "reviewed teaching variant"):
            await self.teach()
        self.complete.assert_not_called()

    async def test_intervention_without_matching_reviewed_candidate_is_configuration_error(self):
        self.decision.kind = "socratic_hint"
        with self.assertRaisesRegex(ValueError, "No reviewed content"):
            await self.teach()
        self.complete.assert_not_called()

    async def test_unknown_provider_does_not_switch_or_call(self):
        with patch.dict(os.environ, {"MODEL_PROVIDER": "openai"}):
            await self.assert_fallback()
        self.complete.assert_not_called()

    async def test_fake_echo_returned_on_bedrock_path_is_rejected(self):
        self.complete.return_value = ProviderResult("[fake provider echo] private prompt", "fake", "fake", 0)
        await self.assert_fallback()

    async def test_next_question_preserved_in_every_return_path(self):
        for next_id in [None, "relationship-q02"]:
            self.decision.next_question_id = next_id
            for mode, outcome, raw in [("bedrock", "correct", json.dumps({"text": self.generated})),
                                       ("bedrock", "incorrect", "invalid"),
                                       ("fake", "incorrect", "unused"),
                                       ("bedrock", "unclear", "unused")]:
                with self.subTest(next_id=next_id, mode=mode, outcome=outcome), patch.dict(os.environ, {"MODEL_PROVIDER": mode}):
                    self.assessment.outcome = outcome
                    self.complete.return_value.text = raw
                    self.assertEqual((await self.teach()).next_question_id, next_id)

    async def test_inputs_and_catalog_are_not_mutated(self):
        def inputs():
            return (self.decision, self.assessment, self.concepts, self.prefs, vars(self.catalog))

        for mode, outcome, raw in [("bedrock", "incorrect", json.dumps({"text": self.generated})),
                                   ("bedrock", "incorrect", "invalid"),
                                   ("fake", "correct", "unused"),
                                   ("bedrock", "unclear", "unused")]:
            with self.subTest(mode=mode, outcome=outcome), patch.dict(os.environ, {"MODEL_PROVIDER": mode}):
                self.assessment.outcome = outcome
                self.complete.return_value.text = raw
                before = copy.deepcopy(inputs())
                await self.teach()
                self.assertEqual(inputs(), before)


if __name__ == "__main__":
    unittest.main()
