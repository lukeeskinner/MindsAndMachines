import unittest
from backend.app.storage.memory import MemoryStore, Session, LearnerProfile
from backend.app.storage.dynamo import DynamoStore
from backend.app.learner.bayesian import BayesianLearner
from backend.tests.storage.test_dynamo import FakeTable


class ProfileStoreTests(unittest.TestCase):
    def test_both_stores_round_trip_separate_beliefs_and_practice(self):
        for store in (MemoryStore(),DynamoStore(FakeTable())):
            with self.subTest(store=type(store).__name__):
                state=BayesianLearner().initial_state(['power']).state
                state.skills['power'].alpha=2
                state.skills['power'].evidence_count=1
                profile=LearnerProfile(state,'calculus',exposed=['fingerprint'],recent=['q1'],session_number=2,active_session_id='s2')
                session=Session('q2',state,course_id='calculus',profile_id='learner',
                                session_start=state.model_copy(deep=True),budget=10,current_review=True)
                store.save_progress('s2',session,'learner',profile)
                self.assertEqual(store.load_profile('learner'),profile)
                self.assertEqual(store.load_session('s2'),session)
                detached=store.load_profile('learner')
                detached.exposed.append('unsaved')
                self.assertEqual(store.load_profile('learner').exposed,['fingerprint'])
                with self.assertRaises(KeyError):store.load_profile('missing')

    def test_dynamo_transaction_failure_does_not_partially_save(self):
        table=FakeTable();store=DynamoStore(table)
        state=BayesianLearner().initial_state(['a']).state
        session=Session('q',state)
        def reject(**_):raise RuntimeError('storage unavailable')
        table.transact_write_items=reject
        with self.assertRaises(RuntimeError):
            store.save_progress('s',session,'p',LearnerProfile(state,None))
        self.assertEqual(table.items,{})
