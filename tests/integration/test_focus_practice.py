import asyncio
import json
from copy import deepcopy
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient
from backend.app.main import create_app
from backend.app.storage.memory import MemoryStore
from backend.app.storage.courses import MemoryCourseRegistry
from backend.tests.ingestion.pool_fixture import pool_course
from backend.app.agents.provider import ProviderResult
from backend.app.teaching.runtime_catalog import build_runtime_catalog
from backend.app.teaching.focus_questions import generate_focus_questions, candidate_passages
from backend.app.policy.focus import rank_focus
from backend.app.learner.bayesian import BayesianLearner


class FocusPracticeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.course = asyncio.run(pool_course())

    def setUp(self):
        self.store = MemoryStore()
        registry = MemoryCourseRegistry()
        registry.register(self.course)
        env = patch.dict('os.environ', {'MODEL_PROVIDER': 'fake', 'DYNAMODB_TABLE_NAME': ''})
        env.start(); self.addCleanup(env.stop)
        with patch('backend.app.main.MemoryStore', return_value=self.store):
            self.client = TestClient(create_app(course_registry=registry))
        self.keys = {q.question_id: q.answer_key for q in self.course.questions}

    def post(self, route, body, status=200):
        r = self.client.post('/api/v1/' + route, json=body)
        self.assertEqual(r.status_code, status, r.text)
        return r.json()

    def start(self, previous=None, reset=False):
        return self.post('sessions', {'course_id': self.course.course_id,
            'previous_session_id': previous, 'reset_learner': reset}, 201)

    def focus(self, session, cid):
        return self.post('focus-practice', {'session_id': session['session_id'], 'concept_id': cid}, 201)

    def answer(self, session, q, answer):
        return self.post('turns', {'session_id': session['session_id'], 'question_id': q['question_id'], 'answer': answer})

    def chat(self, session, message='How did I do and what should I focus on?'):
        return self.post('chat', {'session_id': session['session_id'], 'message': message})

    def complete(self, s):
        q=s['question']; counts={}
        ids=[c.concept_id for c in self.course.concepts]
        while q:
            cid=q['concept_id']; n=counts.get(cid,0); counts[cid]=n+1
            correct=ids.index(cid)==1 or (ids.index(cid) in (0,2) and n%2==0)
            answer=self.keys[q['question_id']] if correct else next(c['id'] for c in q['choices'] if c['id'] not in (self.keys[q['question_id']], 'unsure'))
            r=self.answer(s,q,answer); q=r['next_question']
        return r, counts

    def test_diagnostic_four_each_counts_distinct_posteriors(self):
        s=self.start(); result, counts=self.complete(s)
        self.assertEqual(set(counts.values()), {4})
        self.assertEqual(result['counts']['accepted_observations'],16)
        self.assertEqual(result['counts']['lifetime_evidence'],16)
        self.assertEqual([(c['alpha'],c['beta']) for c in result['concepts']],[(3,3),(5,1),(3,3),(1,5)])
        self.assertEqual(result['analytics']['focus_ranking'][0]['concept_id'], self.course.concepts[-1].concept_id)

    def test_focus_uses_existing_posterior_wrong_unsure_correct_and_counts(self):
        s=self.start(); q=s['question']; cid=q['concept_id']
        r=self.answer(s,q,self.keys[q['question_id']])
        focus=self.focus(s,cid)
        self.assertEqual(focus['concepts'],r['concepts'])
        self.assertEqual(focus['session_start'],r['concepts'])
        seen={q['question_id']}; q=focus['question']; before=self.chat(focus)['analytics']
        for answer_kind in ('correct','wrong','unsure'):
            self.assertFalse(q['review']); self.assertNotIn(q['question_id'],seen); seen.add(q['question_id'])
            answer=(self.keys[q['question_id']] if answer_kind=='correct' else 'unsure' if answer_kind=='unsure' else next(c['id'] for c in q['choices'] if c['id'] not in (self.keys[q['question_id']], 'unsure')))
            r=self.answer(focus,q,answer); q=r['next_question']
        self.assertIsNone(q)
        c=next(c for c in r['concepts'] if c['concept_id']==cid)
        self.assertEqual((c['alpha'],c['beta'],c['evidence_count']),(3,2,3))
        self.assertEqual(r['counts'],dict(submitted_answers=3,unique_questions_seen=3,accepted_observations=2,review_attempts=0,focus_observations=2,lifetime_evidence=3))
        after=self.chat(focus)['analytics']; self.assertNotEqual(before,after)
        again=self.start(focus['session_id']); self.assertEqual(again['concepts'],r['concepts'])
        reset=self.start(again['session_id'],True)
        self.assertTrue(all(c['evidence_count']==0 and c['alpha']==c['beta']==1 for c in reset['concepts']))
        self.assertTrue(all(c['evidence_count']==0 for c in self.chat(reset)['analytics']['focus_ranking']))

    def test_review_generation_failure_preserves_posterior_and_invalid_transitions(self):
        s=self.start(); result,_=self.complete(s); cid=self.course.concepts[-1].concept_id
        f=self.focus(s,cid); self.assertIn('Only review',f['practice_notice'])
        q=f['question']
        while q:
            self.assertTrue(q['review'])
            r=self.answer(f,q,self.keys[q['question_id']]); q=r['next_question']
            self.assertEqual(result['concepts'],r['concepts'])
        self.assertEqual(r['counts']['accepted_observations'],0)
        self.assertEqual(r['counts']['review_attempts'],3)
        self.post('focus-practice',{'session_id':f['session_id'],'concept_id':'foreign'},400)
        self.post('focus-practice',{'session_id':s['session_id'],'concept_id':cid},409)
        self.post('focus-practice',{'session_id':'missing','concept_id':cid},404)

    def test_chat_exact_analytics_no_mutation_and_trusted_action(self):
        s=self.start(); self.complete(s)
        state=deepcopy(self.store.load_session(s['session_id']).learner_state)
        response=self.chat(s,'Give me more practice on my weakest concept.')
        self.assertEqual(response['practice_concept_id'],response['analytics']['focus_ranking'][0]['concept_id'])
        self.assertEqual(self.store.load_session(s['session_id']).learner_state,state)
        for c in response['analytics']['focus_ranking']:
            estimate=next(c2 for c2 in BayesianLearner().describe(state).concepts if c2.concept_id==c['concept_id'])
            self.assertEqual(c['mastery_mean'],estimate.mean)
            self.assertEqual(c['interval90'],estimate.interval90.model_dump())
        mock=AsyncMock(return_value=ProviderResult(json.dumps({'text':'The chain rule needs practice because the estimate is low. Other areas still need evidence.'}),'bedrock','mock',0))
        with patch.dict('os.environ',{'MODEL_PROVIDER':'bedrock'}),patch('backend.app.teaching.chat.provider.complete',mock):
            result=self.chat(s)
        payload=json.loads(mock.call_args.args[0]); self.assertIn('learner_analytics',payload)
        self.assertNotIn('alpha',json.dumps(payload)); self.assertNotIn('answer_key',json.dumps(payload))
        self.assertIn('16.7%',result['text'])
        self.assertEqual(state,self.store.load_session(s['session_id']).learner_state)

    @staticmethod
    async def wording(prompt, **kwargs):
        data=json.loads(prompt)
        result={slot['slot']:{'prompt':slot['prompt'],'assigned_answer_echo':slot['assigned_answer'],
            'wrong_option_1':'Every output stays zero without any calculation.',
            'wrong_option_2':'The original input is always copied unchanged.',
            'wrong_option_3':'The final output is always the square of the input.'} for slot in data['slots']}
        return ProviderResult(json.dumps(result),'bedrock','mock',0)

    def test_bounded_generation_individual_validation_freshness_and_same_beta(self):
        s=self.start(); result,_=self.complete(s); cid=self.course.concepts[-1].concept_id
        generator=AsyncMock(side_effect=self.wording)
        # Mock only content proposals; assessment/learner remain real and local.
        from backend.app.teaching.focus_questions import generate_focus_questions as real_generate
        async def generate(*args):
            with patch.dict('os.environ',{'MODEL_PROVIDER':'bedrock'}),patch('backend.app.teaching.focus_questions.provider.complete',generator):
                return await real_generate(*args)
        with patch('backend.app.api.routes.generate_focus_questions',side_effect=generate):
            f=self.focus(s,cid)
        self.assertEqual(generator.await_count,1)
        self.assertEqual(f['question_count'],3,f['practice_notice'])
        self.assertFalse(f['question']['review'],f['practice_notice'])
        chat_mock=AsyncMock(return_value=ProviderResult(json.dumps({'text':'Consider the inner and outer layers.'}),'bedrock','mock',0))
        with patch.dict('os.environ',{'MODEL_PROVIDER':'bedrock'}),patch('backend.app.teaching.chat.provider.complete',chat_mock):
            self.chat(f,'Explain this differently')
        notes=json.loads(chat_mock.call_args.args[0])['study_notes']
        self.assertTrue(any(note['current_topic'] and 'Chain Rule' in note['topic'] for note in notes))
        q=f['question']; beta=[]
        while q:
            record=self.store.load_profile(self.store.load_session(f['session_id']).profile_id).focus_questions[q['question_id']]
            r=self.answer(f,q,record['question']['answer_key']); q=r['next_question']
            c=next(c for c in r['concepts'] if c['concept_id']==cid); beta.append((c['alpha'],c['beta']))
        self.assertEqual(beta,[(2,5),(3,5),(4,5)])
        self.assertNotEqual(result['analytics']['focus_ranking'][0]['concept_id'],r['analytics']['focus_ranking'][0]['concept_id'])
        self.assertEqual(r['counts']['lifetime_evidence'],19)
        profile=self.store.load_profile(self.store.load_session(f['session_id']).profile_id)
        runtime=build_runtime_catalog(self.course)
        from backend.app.teaching.focus_questions import apply_focus_questions
        apply_focus_questions(runtime,profile)
        later=candidate_passages(runtime,cid,profile,3)
        known=profile.exposed_facts
        self.assertTrue(all(not any(old in p.answers[0][1].casefold() for old in known) for p in later))

    def test_focus_policy_signals_and_deterministic_ties(self):
        concepts=BayesianLearner().initial_state(['a','b']).concepts
        names={'a':'A','b':'B'}
        self.assertEqual([c.concept_id for c in rank_focus(concepts,names)],['a','b'])
        low=deepcopy(concepts); low[1].mean=.1
        self.assertEqual(rank_focus(low,names)[0].concept_id,'b')
        wide=deepcopy(concepts); wide[0].interval90.lower=.4;wide[0].interval90.upper=.6
        self.assertEqual(rank_focus(wide,names)[0].concept_id,'b')
        count=deepcopy(concepts);count[0].evidence_count=4
        self.assertEqual(rank_focus(count,names)[0].concept_id,'b')

    def test_partial_generation_keeps_valid_items_and_never_retries(self):
        s=self.start(); self.complete(s); cid=self.course.concepts[-1].concept_id
        profile=self.store.load_profile(self.store.load_session(s['session_id']).profile_id)
        runtime=build_runtime_catalog(self.course)
        async def mixed(prompt,**kwargs):
            response=await self.wording(prompt,**kwargs)
            data=json.loads(response.text)
            data['item_0']['assigned_answer_echo']='An invented answer'
            data['item_1']['prompt']='Which statement is NOT true?'
            return ProviderResult(json.dumps(data),'bedrock','mock',0)
        mock=AsyncMock(side_effect=mixed)
        with patch.dict('os.environ',{'MODEL_PROVIDER':'bedrock'}),patch('backend.app.teaching.focus_questions.provider.complete',mock):
            generated=asyncio.run(generate_focus_questions(runtime,cid,profile))
        self.assertEqual(mock.await_count,1)
        self.assertEqual(len(generated),1)
        self.assertNotIn(generated[0]['question']['question_id'],self.keys)

    def test_ambiguous_source_distractor_and_provider_failure_are_rejected(self):
        s=self.start(); cid=self.course.concepts[-1].concept_id
        profile=self.store.load_profile(self.store.load_session(s['session_id']).profile_id)
        runtime=build_runtime_catalog(self.course)
        async def ambiguous(prompt,**kwargs):
            response=await self.wording(prompt,**kwargs); data=json.loads(response.text)
            for item in data.values(): item['wrong_option_1']=item['assigned_answer_echo']
            return ProviderResult(json.dumps(data),'bedrock','mock',0)
        for response in (ambiguous,TimeoutError('deadline')):
            mock=AsyncMock(side_effect=response)
            with patch.dict('os.environ',{'MODEL_PROVIDER':'bedrock'}),patch('backend.app.teaching.focus_questions.provider.complete',mock):
                generated=asyncio.run(generate_focus_questions(runtime,cid,profile))
            self.assertEqual(mock.await_count,1);self.assertEqual(generated,[])

    def test_chat_discards_invented_percentages_and_preserves_isolation(self):
        first=self.start();self.complete(first);second=self.start()
        for prose in ('Your mastery is 99%.', "Let's start with the Power Rule instead.",
                      'The derivative is your highest priority.'):
            mock=AsyncMock(return_value=ProviderResult(json.dumps({'text':prose}),'bedrock','mock',0))
            with patch.dict('os.environ',{'MODEL_PROVIDER':'bedrock'}),patch('backend.app.teaching.chat.provider.complete',mock):
                response=self.chat(first)
            self.assertNotIn(prose,response['text']);self.assertEqual(response['teaching_source'],'authored')
        self.assertTrue(all(c['evidence_count']==0 for c in self.chat(second)['analytics']['focus_ranking']))

    def test_exposure_blocks_same_stem_and_source_equivalent_with_new_ids(self):
        from backend.app.teaching.focus_questions import record_exposure, already_exposed
        from backend.app.storage.memory import LearnerProfile
        runtime=build_runtime_catalog(self.course)
        profile=LearnerProfile(BayesianLearner().initial_state(runtime.concept_ids).state,self.course.course_id)
        question=next(iter(runtime.questions.values()))
        record_exposure(profile,question)
        copy=question.model_copy(deep=True);copy.question_id='new-id'
        copy.choices[0].text='Changed distractor'
        self.assertTrue(already_exposed(profile,copy))

    def test_generic_generation_has_no_subject_switch(self):
        from pathlib import Path
        source=Path('backend/app/teaching/focus_questions.py').read_text().casefold()
        self.assertNotIn('calculus',source);self.assertNotIn('chain rule',source)
        self.assertNotIn('.filename',source)
