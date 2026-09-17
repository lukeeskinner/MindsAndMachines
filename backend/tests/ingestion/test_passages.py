"""Grounding comes from trusted reference resolution, never model-copied quotes."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import unittest

from backend.app.ingestion import IngestionError, extract_material
from backend.app.ingestion.passages import (Passage, build_passages, plan_schema, resolve_plan, topic_passages,
                                           fixed_topic_schema, resolve_fixed_topics, repair_slots)
from backend.app.ingestion.pipeline import validate_proposal
from backend.tests.ingestion.helpers import plan_for

FIXTURE = Path(__file__).parent / "fixtures/grad-algorithms.pptx"


class PassagePlanTests(unittest.TestCase):
    def setUp(self):
        self.materials = (extract_material(FIXTURE),)
        self.passages = build_passages(self.materials)
        self.plan = plan_for(self.materials)

    def validate(self, plan):
        return validate_proposal(json.dumps(resolve_plan(plan, self.passages)), self.materials, "test_course")

    def test_source_ids_resolve_exact_evidence_and_preserve_ai_question_text(self):
        self.assertTrue(5 <= len(self.validate(self.plan)[1]) <= 10)
        concepts, questions = self.validate(self.plan)
        self.assertTrue(concepts)
        for concept in concepts:
            self.assertTrue(any(concept.name in r.quote and concept.summary in r.quote for r in concept.source_refs))
        for question in questions:
            answer = next(c.text for c in question.choices if c.id == question.answer_key)
            self.assertTrue(any(answer in r.quote and question.explanation in r.quote for r in question.source_refs))
        self.assertTrue(questions[0].prompt.endswith(self.plan['concepts'][0]['first_question']['prompt']))
        self.assertEqual(questions[0].choices[1].text, self.plan['concepts'][0]['first_question']['wrong_option_1'])
        self.assertNotEqual(questions[0].answer_key, questions[1].answer_key)

    def test_unknown_duplicate_and_wrong_type_passage_ids_rejected(self):
        for value in ("foreign", None, [], 1):
            plan = copy.deepcopy(self.plan)
            plan['concepts'][0]['passage_id'] = value
            with self.subTest(value=value), self.assertRaises(IngestionError):
                self.validate(plan)
        plan = copy.deepcopy(self.plan)
        plan['concepts'] = [plan['concepts'][0]] * 2
        with self.assertRaises(IngestionError):
            self.validate(plan)

    def test_both_question_slots_are_required(self):
        for field in ("first_question", "second_question", "additional_questions"):
            plan = copy.deepcopy(self.plan)
            del plan["concepts"][0][field]
            with self.subTest(field=field), self.assertRaises(IngestionError):
                self.validate(plan)

    def test_exactly_three_wrong_option_fields_are_required(self):
        for field in ("wrong_option_1", "wrong_option_2", "wrong_option_3"):
            plan = copy.deepcopy(self.plan)
            del plan["concepts"][0]["first_question"][field]
            with self.subTest(field=field), self.assertRaises(IngestionError):
                self.validate(plan)
        plan = copy.deepcopy(self.plan)
        plan["concepts"][0]["first_question"]["wrong_option_4"] = "An extra option"
        with self.assertRaises(IngestionError):
            self.validate(plan)

    def test_model_cannot_supply_or_override_answer_ids(self):
        self.assertGreater(len(self.passages), 1)
        for value in (self.passages[1].answers[0][0], 'invented', None, []):
            plan = copy.deepcopy(self.plan)
            plan['concepts'][0]['first_question']['answer_id'] = value
            with self.subTest(value=value), self.assertRaises(IngestionError):
                self.validate(plan)

    def test_each_question_uses_the_exact_server_assigned_slot_answer(self):
        proposal = resolve_plan(self.plan, self.passages)
        passages = {p.passage_id: p for p in self.passages}
        schema = plan_schema(self.passages)
        question_schema = schema["properties"]["concepts"]["items"]["properties"]["first_question"]
        self.assertNotIn("answer_id", question_schema["properties"])
        for planned, resolved in zip(self.plan["concepts"], proposal["concepts"]):
            passage = passages[planned["passage_id"]]
            assigned = passage.public_to_provider()["question_answers"]
            expected = [assigned["first_question"], assigned["second_question"], *assigned["additional_questions"]]
            for index, question in enumerate(resolved["questions"]):
                self.assertEqual(question["choices"][question["answer_index"]], expected[index])
                self.assertEqual(question["explanation"], expected[index])
                self.assertEqual(question["source_refs"][0]["quote"], expected[index])
                self.assertIn(expected[index], passage.text)

    def test_model_cannot_supply_citations_private_fields_or_teaching(self):
        for key in ('source_refs', 'quote', 'explanation', 'answer_index', 'teaching', 'name'):
            plan = copy.deepcopy(self.plan)
            plan['concepts'][0][key] = 'invented'
            with self.subTest(key=key), self.assertRaises(IngestionError):
                self.validate(plan)

    def test_ambiguous_choices_and_answer_in_prompt_still_rejected(self):
        answer = self.passages[0].answers[0][1]
        for change in ({'wrong_option_1': answer}, {'prompt': 'The source says ' + answer}):
            plan = copy.deepcopy(self.plan)
            plan['concepts'][0]['first_question'].update(change)
            with self.subTest(change=tuple(change)), self.assertRaises(IngestionError):
                self.validate(plan)

    def test_misconception_seeking_stems_cannot_reverse_the_source_answer(self):
        for prompt in ("What is a common misunderstanding about derivatives?",
                       "Which statement is false about this topic?",
                       "Which statement is not supported?"):
            plan = copy.deepcopy(self.plan)
            plan["concepts"][0]["first_question"]["prompt"] = prompt
            with self.subTest(prompt=prompt), self.assertRaisesRegex(IngestionError, "false or mistaken"):
                self.validate(plan)

    def test_true_alternative_from_another_concept_sentence_is_ambiguous(self):
        text = "Power rule multiplies by the exponent. Constant coefficients remain in front."
        chunk = replace(self.materials[0].chunks[0], text=text, normalized_text=text)
        materials = (replace(self.materials[0], chunks=(chunk,)),)
        passage = Passage("p1", chunk.chunk_id, text, "Power rule", (
            ("p1_a1", "Power rule multiplies by the exponent."),
            ("p1_a2", "Constant coefficients remain in front.")))
        plan = {"concepts": [copy.deepcopy(self.plan["concepts"][0])]}
        plan["concepts"][0]["passage_id"] = "p1"
        for distractor in ("MULTIPLIES BY THE EXPONENT",
                           "CONSTANT COEFFICIENTS REMAIN IN FRONT."):
            plan["concepts"][0]["first_question"]["wrong_option_1"] = distractor
            with self.subTest(distractor=distractor), self.assertRaisesRegex(IngestionError, "ambiguous"):
                validate_proposal(json.dumps(resolve_plan(plan, (passage,))), materials, "test_course")

    def test_numbered_topics_narrow_context_without_changing_source_assignments(self):
        def passage(key, label):
            return Passage(key, "chunk", label + " First definition. Second fact.", label,
                           ((key + "a", "First definition."), (key + "b", "Second fact.")))
        first, second = passage("p1", "1. Power Rule"), passage("p3", "2. Chain Rule")
        generic = passage("p2", "Useful comparison")
        selected = topic_passages((first, generic, second))
        self.assertEqual(selected, (first, second))
        self.assertIs(selected[0], first)
        self.assertEqual(topic_passages((first, generic)), ())
        self.assertEqual(len(fixed_topic_schema(selected)["required"]), 4)

    def test_formula_distractor_cannot_evade_overlap_with_terminal_punctuation(self):
        text = "Power Rule: f'(x) = n x^(n-1): multiply by the exponent. Constants stay in front."
        chunk = replace(self.materials[0].chunks[0], text=text, normalized_text=text)
        materials = (replace(self.materials[0], chunks=(chunk,)),)
        passage = Passage("p1", chunk.chunk_id, text, "Power Rule", (("a", text),))
        plan = {"concepts": [copy.deepcopy(self.plan["concepts"][0])]}
        plan["concepts"][0]["passage_id"] = "p1"
        item = plan["concepts"][0]["first_question"]
        item["wrong_option_1"] = "f'(x) = n x^(n-1)."
        with self.assertRaisesRegex(IngestionError, "ambiguous"):
            validate_proposal(json.dumps(resolve_plan(plan, (passage,))), materials, "test_course")
        item["wrong_option_1"] = "f'(x) = n x^(n+1)."
        self.assertTrue(validate_proposal(json.dumps(resolve_plan(plan, (passage,))), materials, "test_course")[1])

    def test_fixed_slots_and_repairs_preserve_topic_and_answer_mapping(self):
        passages = self.passages[:2]
        schema = fixed_topic_schema(passages)
        wording = {"prompt": "Which statement applies?", "wrong_option_1": "A wrong statement.",
                   "wrong_option_2": "A different wrong statement.", "wrong_option_3": "Another wrong statement."}
        response = {key: {**wording, "prompt": key} for key in schema["required"]}
        plan = resolve_fixed_topics(response, passages)
        for ci, passage in enumerate(passages):
            self.assertEqual(plan["concepts"][ci]["passage_id"], passage.passage_id)
            for qi, field in enumerate(("first_question", "second_question")):
                key = f"topic_{ci + 1}_question_{qi + 1}"
                self.assertEqual(plan["concepts"][ci][field]["prompt"], key)
                self.assertIn(passage.answer_for_slot(qi), schema["properties"][key]["description"])
        targets = ["/concepts/1/first_question", "/concepts/0/second_question"]
        assignments = {s["question_id"]: s for s in repair_slots(plan, passages, targets)}
        self.assertEqual(assignments[targets[0]]["assigned_answer"], passages[1].answer_for_slot(0))
        self.assertEqual(assignments[targets[1]]["assigned_answer"], passages[0].answer_for_slot(1))
        with self.assertRaises(IngestionError):
            resolve_fixed_topics({**response, "passage_id": "foreign"}, passages)

    def test_answer_echo_cannot_change_the_trusted_answer(self):
        plan = copy.deepcopy(self.plan)
        passage = next(p for p in self.passages if p.passage_id == plan['concepts'][0]['passage_id'])
        item = plan['concepts'][0]['first_question']
        original = self.validate(plan)[1]
        item['assigned_answer_echo'] = passage.answer_for_slot(0)
        self.assertEqual(self.validate(plan)[1], original)
        for echo in ('An invented answer.', passage.answer_for_slot(0).upper(), None):
            item['assigned_answer_echo'] = echo
            with self.subTest(echo=echo), self.assertRaisesRegex(IngestionError, 'answer ID'):
                self.validate(plan)

    def test_stem_guard_reports_exact_keyword_even_in_positive_phrasing(self):
        from backend.app.ingestion.passages import FORBIDDEN_STEM_WORDS, QuestionValidationError
        for word in FORBIDDEN_STEM_WORDS:
            plan = copy.deepcopy(self.plan)
            plan["concepts"][0]["first_question"]["prompt"] = f"Which accurate statement explains the term {word.upper()}?"
            with self.subTest(word=word), self.assertRaises(QuestionValidationError) as caught:
                resolve_plan(plan, self.passages)
            self.assertEqual(caught.exception.failures[0]["matched_keywords"], [word])
            self.assertEqual(caught.exception.failures[0]["rule"], "forbidden_whole_word_in_prompt")

    def test_invalid_distractors_are_not_repaired_or_dropped(self):
        for value in ([], None, 12, 'x' * 1201, ''):
            plan = copy.deepcopy(self.plan)
            plan['concepts'][0]['first_question']['wrong_option_1'] = value
            with self.subTest(value=str(value)[:20]), self.assertRaises(IngestionError):
                self.validate(plan)

    def test_invalid_plan_sizes_identify_the_list_without_accepting_partial_content(self):
        for field, values, reason in (
            ("concepts", [], "concept list"),
        ):
            plan = copy.deepcopy(self.plan)
            target = plan if field == "concepts" else plan['concepts'][0]
            target[field] = values
            with self.subTest(field=field), self.assertRaisesRegex(IngestionError, reason):
                self.validate(plan)

    def test_bank_accepts_short_generation_and_keeps_upper_bound(self):
        passages = tuple(Passage(f"p{i}", f"chunk{i}", "A useful source statement.", f"Topic {i}",
                                 ((f"a{i}", "A useful source statement."),)) for i in range(5))
        def concept(i, extra):
            question = {"prompt": "What does this source explain?",
                        "wrong_option_1": "A different explanation.", "wrong_option_2": "Another explanation.",
                        "wrong_option_3": "An unrelated explanation."}
            return {"passage_id": f"p{i}", "first_question": question, "second_question": question,
                    "additional_questions": [question.copy() for _ in range(extra)]}
        for count, extra, expected in ((1, 0, 2), (1, 3, 5), (5, 0, 10)):
            result = resolve_plan({"concepts": [concept(i, extra) for i in range(count)]}, passages)
            self.assertEqual(sum(len(c["questions"]) for c in result["concepts"]), expected)
        with self.assertRaisesRegex(IngestionError, "exceeds ten"):
            resolve_plan({"concepts": [concept(0, 1), *[concept(i, 0) for i in range(1, 5)]]}, passages)

    def test_source_windows_preserve_source_and_stable_ids(self):
        text = ('A long sentence describing a mathematical relationship. ' * 50).strip()
        chunk = replace(self.materials[0].chunks[0], text=text, normalized_text=text)
        materials = (replace(self.materials[0], chunks=(chunk,)),)
        first = build_passages(materials)
        self.assertEqual(first, build_passages(materials))
        self.assertGreater(len(first), 1)
        for passage in first:
            self.assertLessEqual(len(passage.text), 800)
            self.assertIn(passage.text, text)
            self.assertIn(passage.label, passage.text)
            for _, answer in passage.answers:
                self.assertIn(answer, passage.text)
        self.assertEqual(chunk.normalized_text, text)

    def test_source_heading_is_not_offered_as_an_answer_disclosed_by_label(self):
        text = "The Power Rule\n\nA derivative measures the instantaneous rate of change."
        chunk = replace(self.materials[0].chunks[0], text=text,
                        normalized_text="The Power Rule A derivative measures the instantaneous rate of change.")
        passages = build_passages((replace(self.materials[0], chunks=(chunk,)),))
        self.assertTrue(passages)
        for passage in passages:
            for _, answer in passage.answers:
                self.assertNotIn(answer, passage.label)
                self.assertNotEqual(answer, "The Power Rule")
