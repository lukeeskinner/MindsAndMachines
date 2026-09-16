import unittest
from unittest.mock import AsyncMock, Mock

from backend.app.agents.assessor import FakeAssessor
from backend.app.agents.coordinator import Coordinator, IntegrationError
from backend.app.learner.bayesian import BayesianLearner
from backend.app.policy.adaptive import AdaptivePolicy
from backend.app.teaching.catalog import Catalog
from contracts.models import TeachingResult, TurnRequest


class CoordinatorAuthorityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.learner = BayesianLearner()
        self.initial = self.learner.initial_state(self.catalog.concept_ids)
        self.question = self.catalog.question(self.catalog.first_question_id)
        self.request = TurnRequest(session_id="test", question_id=self.question.question_id, answer="a")
        self.teaching = Mock(teach=AsyncMock())
        self.coordinator = Coordinator(FakeAssessor(), self.learner, AdaptivePolicy(), self.teaching)

    async def run_turn(self):
        return await self.coordinator.run_turn(self.request, self.question, self.initial.state, [],
                                               self.catalog.candidates, self.catalog.questions)

    async def test_mutating_teaching_cannot_rewrite_policy_or_estimates(self):
        assessment = await self.coordinator.assessor.assess(self.question, "a")
        update = self.learner.update(self.initial.state, assessment, [])
        decision = self.coordinator.policy.choose(update.concepts, assessment, self.catalog.candidates, [])
        original = decision.model_copy(deep=True)
        self.coordinator.policy = Mock(choose=Mock(return_value=decision))

        async def malicious(decision, assessment, concepts, preferences):
            decision.candidate_id = "attacker"
            decision.content_id = "attacker"
            decision.concept_id = "bfs"
            decision.kind = "diagnostic_probe"
            decision.reason = "attacker controls policy"
            decision.next_question_id = "relationship-q01"
            assessment.feedback = "attacker"
            concepts[-1].mean = 1
            return TeachingResult(text="test", next_question_id=original.next_question_id, fallback=False)

        self.teaching.teach.side_effect = malicious
        result_update, response = await self.run_turn()
        self.assertEqual(decision, original)
        self.assertEqual(response.decision.model_dump(), original.model_dump(
            include={"candidate_id", "concept_id", "kind", "reason"}))
        self.assertEqual(response.next_question.question_id, original.next_question_id)
        self.assertEqual(response.concepts, update.concepts)
        self.assertEqual(result_update, update)
        self.assertEqual(response.assessment.feedback, assessment.feedback)

    async def test_mutation_and_matching_forged_result_are_rejected(self):
        async def malicious(decision, *args):
            decision.next_question_id = "relationship-q01"
            return TeachingResult(text="test", next_question_id=decision.next_question_id, fallback=False)

        self.teaching.teach.side_effect = malicious
        with self.assertRaisesRegex(IntegrationError, "changed"):
            await self.run_turn()

    async def test_plain_mismatch_is_rejected(self):
        self.teaching.teach.return_value = TeachingResult(text="test", next_question_id=None, fallback=False)
        with self.assertRaisesRegex(IntegrationError, "changed"):
            await self.run_turn()

    async def test_unknown_policy_question_fails_before_teaching(self):
        del self.catalog.questions["relationship-q02"]
        with self.assertRaisesRegex(IntegrationError, "unknown next question"):
            await self.run_turn()
        self.teaching.teach.assert_not_called()
