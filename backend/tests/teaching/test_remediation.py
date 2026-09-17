"""Shared focus and card priority use trusted evidence, never review clicks."""
from copy import deepcopy
import unittest

from backend.app.agents.real_assessor import RealAssessor
from backend.app.learner.bayesian import BayesianLearner
from backend.app.policy.adaptive import AdaptivePolicy
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.flashcards import demo_flashcards
from backend.app.teaching.remediation import derive_focus, rank_flashcards, should_generate
from contracts.models import Assessment


class SharedRemediationTests(unittest.IsolatedAsyncioTestCase):
    async def test_reviewed_misconception_drives_policy_focus_and_existing_card(self):
        catalog = Catalog()
        learner = BayesianLearner()
        initial = learner.initial_state(catalog.concept_ids)
        question = catalog.question(catalog.first_question_id)
        assessment = await RealAssessor().assess(question, "a")
        update = learner.update(initial.state, assessment, [])
        focus = derive_focus(None, assessment, update.evidence_applied, question.question_id, None)
        decision = AdaptivePolicy().choose(update.concepts, assessment, catalog.candidates, [])
        self.assertEqual(focus.misconception_id, "admissible_means_consistent")
        self.assertEqual(decision.concept_id, focus.concept_id)
        self.assertTrue(should_generate(focus, assessment, True, decision))
        self.assertNotEqual(decision.next_question_id, question.question_id)
        # Place a generic card first to prove the tag breaks ties within concept.
        cards = list(reversed(demo_flashcards()))
        before = deepcopy(update)
        ranked = rank_flashcards(cards, update.concepts, focus, None)
        self.assertEqual(ranked[0].card_id, "demo-card-6")
        self.assertEqual(update, before)
        self.assertEqual(cards, list(reversed(demo_flashcards())))
        # No diagnosis still targets the concept, preserving within-concept order.
        generic = focus.model_copy(update={"misconception_id": None})
        self.assertEqual(rank_flashcards(cards, update.concepts, generic, None)[0].card_id, "demo-card-7")

    async def test_low_mastery_ranks_first_and_card_projection_is_read_only(self):
        learner = BayesianLearner()
        initial = learner.initial_state(["bfs", "ucs"])
        good = Assessment(outcome="correct", concept_id="bfs", score=1, misconception_id=None, feedback="")
        bad = good.model_copy(update={"outcome": "incorrect", "score": 0, "concept_id": "ucs"})
        update = learner.update(learner.update(initial.state, good, []).state, bad, [])
        cards = demo_flashcards()[:2]
        before = deepcopy(update.state)
        for _ in range(3):
            self.assertEqual(rank_flashcards(cards, update.concepts, None, None)[0].concept_id, "ucs")
        self.assertEqual(update.state, before)
        self.assertEqual(rank_flashcards(cards, initial.concepts, None, None), cards)

    async def test_unclear_keeps_prior_focus_without_inventing_evidence_and_correct_clears_it(self):
        learner = BayesianLearner()
        initial = learner.initial_state(["x"])
        bad = Assessment(outcome="incorrect", concept_id="x", score=0, misconception_id=None, feedback="")
        focus = derive_focus(None, bad, True, "q", "course")
        unclear = bad.model_copy(update={"outcome": "unclear", "score": None})
        update = learner.update(initial.state, unclear, [])
        self.assertFalse(update.evidence_applied)
        self.assertIsNone(derive_focus(None, unclear, False, "q", "course"))
        self.assertEqual(derive_focus(focus, unclear, False, "q2", "course"), focus)
        self.assertFalse(should_generate(focus, unclear, False, None))
        self.assertIsNone(derive_focus(focus, bad.model_copy(update={"outcome": "correct", "score": 1}),
                                       True, "q2", "course"))
        cards = demo_flashcards()
        self.assertEqual(rank_flashcards(cards, [], focus, "foreign"), cards)
