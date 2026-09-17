import copy,json,unittest
from unittest.mock import AsyncMock,patch
from backend.app.agents.provider import ProviderResult
from backend.app.ingestion import process_course,IngestionError
from backend.tests.ingestion.pool_fixture import CALCULUS,wording
from backend.app.ingestion.passages import topic_passages,build_passages
from backend.app.ingestion.extraction import extract_material

class PoolGenerationTests(unittest.IsolatedAsyncioTestCase):
    async def test_safe_partial_pool_keeps_three_and_one_bounded_repair(self):
        proposal=wording()
        proposal['topic_1_question_4']['prompt']='Which statement is false?'
        fake=AsyncMock(side_effect=[ProviderResult(json.dumps(proposal),'bedrock','mock',0),
                                  ProviderResult('{"repairs":[]}','bedrock','mock',0)])
        with patch.dict('os.environ',{'MODEL_PROVIDER':'bedrock'}),patch('backend.app.ingestion.pipeline.provider.complete',fake):
            course=await process_course([CALCULUS])
        self.assertEqual(fake.await_count,2)
        self.assertEqual(len(course.questions),15)
        self.assertEqual(course.metadata.discarded_question_count,1)
        self.assertEqual(course.metadata.schema_version,'2')

    async def test_reject_pool_below_three_without_weakening_validator(self):
        proposal=wording()
        for i in (3,4):proposal[f'topic_1_question_{i}']['prompt']='Which statement is false?'
        fake=AsyncMock(side_effect=[ProviderResult(json.dumps(proposal),'bedrock','mock',0),
                                  ProviderResult('{"repairs":[]}','bedrock','mock',0)])
        with patch.dict('os.environ',{'MODEL_PROVIDER':'bedrock'}),patch('backend.app.ingestion.pipeline.provider.complete',fake):
            with self.assertRaisesRegex(IngestionError,'fewer than three'):
                await process_course([CALCULUS])
        self.assertEqual(fake.await_count,2)

    def test_example_and_purpose_assignments_are_exact_and_distinct(self):
        material=extract_material(CALCULUS)
        passages=topic_passages(build_passages((material,)))
        self.assertEqual(len(passages),4)
        for p in passages:
            self.assertEqual(len(set(p.answer_for_slot(i) for i in range(4))),4)
            for i in range(4):
                self.assertTrue(any(p.answer_for_slot(i) in c.normalized_text for c in material.chunks))

    async def test_source_task_cannot_be_replaced_by_an_unchecked_semantic_question(self):
        proposal=wording()
        proposal['topic_3_question_3']['wrong_option_3']="The derivative is 2x sin(x) + x^2 cos(x)."
        proposal['topic_3_question_3']['prompt'] = "Which expression gives the result?"
        fake=AsyncMock(side_effect=[ProviderResult(json.dumps(proposal),'bedrock','mock',0),
                                  ProviderResult('{"repairs":[]}','bedrock','mock',0)])
        with patch.dict('os.environ',{'MODEL_PROVIDER':'bedrock'}),patch('backend.app.ingestion.pipeline.provider.complete',fake):
            course=await process_course([CALCULUS])
        self.assertEqual(course.metadata.discarded_question_count,1)
        self.assertEqual(len(course.questions),15)
        self.assertFalse(any(q.prompt.endswith(proposal['topic_3_question_3']['prompt']) for q in course.questions))
        self.assertEqual(fake.await_count,2)
