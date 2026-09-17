"""Grounding comes from trusted reference resolution, never model-copied quotes."""
import copy
from dataclasses import replace
import json
from pathlib import Path
import unittest

from backend.app.ingestion import IngestionError, extract_material
from backend.app.ingestion.passages import Passage, build_passages, resolve_plan
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

    def test_cross_passage_and_unknown_answer_ids_rejected(self):
        self.assertGreater(len(self.passages), 1)
        for value in (self.passages[1].answers[0][0], 'invented', None, []):
            plan = copy.deepcopy(self.plan)
            plan['concepts'][0]['first_question']['answer_id'] = value
            with self.subTest(value=value), self.assertRaises(IngestionError):
                self.validate(plan)

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

    def test_bank_accepts_five_and_ten_questions_and_rejects_outside_bounds(self):
        passages = tuple(Passage(f"p{i}", f"chunk{i}", "A useful source statement.", f"Topic {i}",
                                 ((f"a{i}", "A useful source statement."),)) for i in range(5))
        def concept(i, extra):
            question = {"prompt": "What does this source explain?", "answer_id": f"a{i}",
                        "wrong_option_1": "A different explanation.", "wrong_option_2": "Another explanation.",
                        "wrong_option_3": "An unrelated explanation."}
            return {"passage_id": f"p{i}", "first_question": question, "second_question": question,
                    "additional_questions": [question.copy() for _ in range(extra)]}
        for count, extra, expected in ((1, 3, 5), (5, 0, 10)):
            result = resolve_plan({"concepts": [concept(i, extra) for i in range(count)]}, passages)
            self.assertEqual(sum(len(c["questions"]) for c in result["concepts"]), expected)
        for concepts in ([concept(0, 0)], [concept(0, 1), *[concept(i, 0) for i in range(1, 5)]]):
            with self.assertRaisesRegex(IngestionError, "5–10"):
                resolve_plan({"concepts": concepts}, passages)

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
