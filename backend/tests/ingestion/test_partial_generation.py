"""Mixed live failure patterns with mocked Bedrock: quality gates never relax."""
import copy
import json
import os
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.agents.provider import ProviderError, ProviderResult
from backend.app.ingestion import IngestionError, extract_material, process_course
from backend.app.ingestion.passages import build_passages, resolve_plan
from backend.app.ingestion.pipeline import _inspect_plan
from backend.tests.ingestion.helpers import plan_for

FIXTURES = Path(__file__).parent / 'fixtures'


class PartialGenerationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.paths = [FIXTURES / 'course.pdf', FIXTURES / 'course.pptx']
        self.materials = tuple(extract_material(p) for p in self.paths)
        self.passages = build_passages(self.materials)
        self.valid = plan_for(self.materials)
        self.bank = copy.deepcopy(self.valid)
        self.bank['concepts'][0]['second_question']['answer_id'] = 'foreign_answer'
        self.bank['concepts'][1]['additional_questions'].append(copy.deepcopy(self.bank['concepts'][1]['first_question']))
        answer = next(p for p in self.passages if p.passage_id == self.bank['concepts'][2]['passage_id']).answer_for_slot(1)
        self.bank['concepts'][2]['second_question']['wrong_option_1'] = ' '.join(answer.split()[1:4])
        self.bank['concepts'][3]['second_question']['prompt'] = 'Which statement is incorrect?'
        self.targets = ['/concepts/0/second_question', '/concepts/1/additional_questions/0',
                        '/concepts/2/second_question', '/concepts/3/second_question']
        self.provider = AsyncMock()
        for patcher in (patch.dict(os.environ, {'MODEL_PROVIDER': 'bedrock'}),
                        patch('backend.app.ingestion.pipeline.provider.complete', self.provider)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def result(self, plan):
        return ProviderResult(json.dumps(plan), 'bedrock', 'mock', 0)

    def question(self, plan, target):
        value = plan
        for part in target.split('/')[1:]:
            value = value[int(part)] if isinstance(value, list) else value[part]
        return copy.deepcopy(value)

    def repairs(self, valid=False):
        questions = [self.question(self.bank, t) for t in self.targets]
        if valid:
            questions = [copy.deepcopy(self.valid['concepts'][0]['second_question']),
                         {**questions[1], 'prompt': 'Which statement describes the admissibility condition?'},
                         copy.deepcopy(self.valid['concepts'][2]['second_question']),
                         copy.deepcopy(self.valid['concepts'][3]['second_question'])]
        return {'repairs': [{'question_id': t, 'question': q} for t, q in zip(self.targets, questions)]}

    async def test_mixed_invalid_bank_accepts_only_valid_survivors_after_failed_repair(self):
        expected, failures, accepted = _inspect_plan(self.bank, self.passages, self.materials, 'test')
        self.assertEqual({f['reason'] for f in failures}, {'invalid_answer_reference', 'duplicate_question_content',
                                                       'ambiguous_question', 'negative_question'})
        self.assertEqual(set(self.targets), {f['question_id'] for f in failures})
        self.provider.side_effect = [self.result(self.bank), self.result(self.repairs())]
        course = await process_course(self.paths)
        self.assertEqual(self.provider.await_count, 2)
        self.assertEqual(len(course.questions), 5)
        self.assertTrue(course.metadata.degraded)
        self.assertEqual(course.metadata.discarded_question_count, 4)
        self.assertEqual(course.metadata.repaired_question_count, 0)
        self.assertEqual([q.prompt for q in course.questions], [q.prompt for q in expected[1]])
        self.assertEqual([q.source_refs for q in course.questions], [q.source_refs for q in expected[1]])
        feedback = json.loads(self.provider.call_args.args[0])['revision']
        self.assertEqual(set(feedback['repair_targets']), set(self.targets))
        self.assertEqual(len(accepted), 5)

    async def test_all_four_failure_types_can_be_repaired_in_one_call(self):
        self.provider.side_effect = [self.result(self.bank), self.result(self.repairs(valid=True))]
        course = await process_course(self.paths)
        self.assertEqual(self.provider.await_count, 2)
        self.assertEqual(len(course.questions), 9)
        self.assertFalse(course.metadata.degraded)
        self.assertEqual(course.metadata.repaired_question_count, 4)
        self.assertEqual(course.metadata.discarded_question_count, 0)
        initial, _, _ = _inspect_plan(self.bank, self.passages, self.materials, course.course_id)
        self.assertTrue(set(initial[1]).issubset(set(course.questions)))

    async def test_fixed_topic_generation_repairs_only_the_bound_question_slot(self):
        selected = tuple(next(p for p in self.passages if p.passage_id == c['passage_id'])
                         for c in self.valid['concepts'])
        wording = {f'topic_{ci + 1}_question_{qi + 1}': copy.deepcopy(c[field])
                   for ci, c in enumerate(self.valid['concepts'])
                   for qi, field in enumerate(('first_question', 'second_question'))}
        wording['topic_2_question_1']['prompt'] = 'Which statement is false?'
        target = '/concepts/1/first_question'
        repair = {'repairs': [{'question_id': target,
                              'question': self.valid['concepts'][1]['first_question']}]}
        self.provider.side_effect = [self.result(wording), self.result(repair)]
        with patch('backend.app.ingestion.pipeline.topic_passages', return_value=selected):
            course = await process_course(self.paths)
        self.assertEqual((len(course.concepts), len(course.questions)), (len(selected), 2 * len(selected)))
        self.assertEqual((course.metadata.provider_calls, course.metadata.repaired_question_count,
                          course.metadata.discarded_question_count), (2, 1, 0))
        payload = json.loads(self.provider.call_args.args[0])
        self.assertEqual(payload['repair_slots'], [{'question_id': target, 'topic': selected[1].label,
                         'source_text': selected[1].text, 'assigned_answer': selected[1].answer_for_slot(0)}])
        repaired = course.questions[2]
        self.assertEqual(next(c.text for c in repaired.choices if c.id == repaired.answer_key),
                         selected[1].answer_for_slot(0))

    async def test_some_repairs_invalid_preserves_successful_repairs_and_original_valid_items(self):
        response = self.repairs(valid=True)
        response['repairs'][0]['question'] = {'prompt': 'Malformed repair'}
        self.provider.side_effect = [self.result(self.bank), self.result(response)]
        course = await process_course(self.paths)
        self.assertEqual((len(course.questions), course.metadata.repaired_question_count,
                          course.metadata.discarded_question_count), (8, 3, 1))
        initial, _, _ = _inspect_plan(self.bank, self.passages, self.materials, course.course_id)
        self.assertTrue(set(initial[1]).issubset(set(course.questions)))

    async def test_empty_concept_after_repair_rejects_entire_course(self):
        self.bank['concepts'][0]['first_question']['prompt'] = 'Which statement is false?'
        self.provider.side_effect = [self.result(self.bank), self.result({'repairs': []})]
        with self.assertRaisesRegex(IngestionError, 'at least one usable grounded question'):
            await process_course(self.paths)
        self.assertEqual(self.provider.await_count, 2)

    async def test_unknown_passage_and_untrusted_course_structure_are_fatal_without_repair(self):
        for mutate in ('passage', 'concept', 'extra'):
            bank = copy.deepcopy(self.bank)
            if mutate == 'passage':
                bank['concepts'][0]['passage_id'] = 'foreign'
            elif mutate == 'concept':
                bank['concepts'][1]['passage_id'] = bank['concepts'][0]['passage_id']
            else:
                bank['concepts'][0]['source_refs'] = []
            self.provider.reset_mock()
            self.provider.side_effect = [self.result(bank)]
            with self.subTest(mutate=mutate), self.assertRaises(IngestionError):
                await process_course(self.paths)
            self.assertEqual(self.provider.await_count, 1)

    async def test_trusted_answer_or_source_integrity_failure_is_fatal(self):
        for bad in (replace(self.passages[0], chunk_id='foreign'),
                    replace(self.passages[0], answers=(('answer', 'Fabricated source answer.'),))):
            self.provider.reset_mock()
            self.provider.side_effect = [self.result(self.bank)]
            with self.subTest(bad=bad.chunk_id), patch('backend.app.ingestion.pipeline.build_passages',
                    return_value=(bad, *self.passages[1:])):
                with self.assertRaises(IngestionError):
                    await process_course(self.paths)
            self.assertEqual(self.provider.await_count, 1)

    async def test_repair_provider_failure_or_invalid_envelope_keeps_initial_valid_bank(self):
        for failure in (ProviderError('private error'), self.result({'repairs': []}), self.result(self.bank)):
            self.provider.reset_mock()
            self.provider.side_effect = [self.result(self.bank), failure]
            course = await process_course(self.paths)
            self.assertEqual((len(course.questions), course.metadata.discarded_question_count,
                              course.metadata.repaired_question_count), (5, 4, 0))
            self.assertNotIn('private error', str(course.metadata))
            self.assertEqual(self.provider.await_count, 2)

    async def test_single_remaining_question_is_valid_runtime_minimum(self):
        bank = {'concepts': [copy.deepcopy(self.valid['concepts'][0])]}
        bank['concepts'][0]['second_question']['prompt'] = 'Which statement is false?'
        self.provider.side_effect = [self.result(bank), self.result({'repairs': []})]
        course = await process_course(self.paths)
        self.assertEqual((len(course.concepts), len(course.questions)), (1, 1))
        self.assertTrue(course.metadata.degraded)

    async def test_repaired_duplicate_cannot_displace_original_valid_later_slot(self):
        bank = {'concepts': [copy.deepcopy(self.valid['concepts'][0])]}
        valid = copy.deepcopy(bank['concepts'][0]['first_question'])
        bank['concepts'][0]['additional_questions'] = [valid]
        bank['concepts'][0]['first_question']['prompt'] = 'Which statement is false?'
        response = {'repairs': [{'question_id': '/concepts/0/first_question', 'question': valid}]}
        self.provider.side_effect = [self.result(bank), self.result(response)]
        course = await process_course(self.paths)
        self.assertEqual((len(course.questions), course.metadata.repaired_question_count), (2, 0))
        # The extra slot keeps its assigned correct-choice position c, not a.
        retained = next(q for q in course.questions if q.prompt.endswith(valid['prompt']))
        self.assertEqual(retained.answer_key, 'c')

    async def test_answer_leakage_and_duplicate_choices_are_omitted_not_accepted(self):
        for changes in ({'prompt': 'The source says ' + self.passages[0].answer_for_slot(0)},
                        {'wrong_option_1': 'identical', 'wrong_option_2': 'IDENTICAL'}):
            bank = copy.deepcopy(self.valid)
            bank['concepts'][0]['first_question'].update(changes)
            with self.assertRaises(IngestionError):
                # Strict validator remains authoritative outside the ingestion collector.
                resolved = resolve_plan(bank, self.passages)
                from backend.app.ingestion.pipeline import validate_proposal
                validate_proposal(json.dumps(resolved), self.materials, 'test')
            self.provider.side_effect = [self.result(bank), self.result({'repairs': []})]
            course = await process_course(self.paths)
            self.assertEqual(len(course.questions), 7)
            self.assertTrue(course.metadata.degraded)
