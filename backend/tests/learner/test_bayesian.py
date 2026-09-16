import math
import unittest

from backend.app.learner.bayesian import BayesianLearner, _beta_cdf, _beta_quantile
from contracts.models import Assessment, HistoryEntry, LearnerState, SkillState


def assessment(score, concept_id="a"):
    return Assessment(
        outcome={1: "correct", 0: "incorrect", None: "unclear"}[score],
        concept_id=concept_id, score=score, misconception_id=None, feedback="Test evidence",
    )


class BayesianLearnerTests(unittest.TestCase):
    def setUp(self):
        self.learner = BayesianLearner()

    def assert_posterior(self, result, alpha, beta, count, interval=None):
        self.assertEqual(result.state.skills["a"],
                         SkillState(alpha=alpha, beta=beta, evidence_count=count))
        concept = next(c for c in result.concepts if c.concept_id == "a")
        self.assertEqual(concept.mean, alpha / (alpha + beta))
        self.assertEqual(concept.evidence_count, count)
        self.assertLessEqual(0, concept.interval90.lower)
        self.assertLessEqual(concept.interval90.lower, concept.interval90.upper)
        self.assertLessEqual(concept.interval90.upper, 1)
        if interval is not None:
            self.assertEqual((concept.interval90.lower, concept.interval90.upper), interval)

    def test_initial_prior(self):
        result = self.learner.initial_state(["a", "b"])
        self.assertFalse(result.evidence_applied)
        for concept in result.concepts:
            self.assertEqual(result.state.skills[concept.concept_id],
                             SkillState(alpha=1, beta=1, evidence_count=0))
            self.assertEqual(concept.mean, 0.5)
            self.assertEqual(concept.evidence_count, 0)
            self.assertEqual(concept.interval90.model_dump(), {"lower": 0.05, "upper": 0.95})
        self.assertIsNot(result.state.skills["a"], result.state.skills["b"])

    def test_initial_order_and_independent_calls(self):
        first = self.learner.initial_state(["z", "a", "custom-concept"])
        second = self.learner.initial_state(["z", "a", "custom-concept"])
        self.assertEqual([c.concept_id for c in first.concepts], ["z", "a", "custom-concept"])
        first.state.skills["a"].alpha = 2
        self.assertEqual(second.state.skills["a"].alpha, 1)
        self.assertEqual(first.state.skills["z"].alpha, 1)

    def test_empty_initial_state(self):
        result = self.learner.initial_state([])
        self.assertEqual(result.state.skills, {})
        self.assertEqual(result.concepts, [])
        self.assertFalse(result.evidence_applied)

    def test_first_incorrect(self):
        result = self.learner.update(self.learner.initial_state(["a"]).state, assessment(0), [])
        self.assert_posterior(result, 1, 2, 1, (0.0253, 0.7764))
        self.assertTrue(result.evidence_applied)

    def test_correct_first(self):
        result = self.learner.update(self.learner.initial_state(["a"]).state, assessment(1), [])
        self.assert_posterior(result, 2, 1, 1, (0.2236, 0.9747))
        self.assertTrue(result.evidence_applied)

    def test_incorrect_then_correct(self):
        first = self.learner.update(self.learner.initial_state(["a"]).state, assessment(0), [])
        result = self.learner.update(first.state, assessment(1), [])
        self.assert_posterior(result, 2, 2, 2, (0.1354, 0.8646))
        self.assertTrue(result.evidence_applied)

    def test_general_sequence(self):
        result = self.learner.initial_state(["a"])
        successes = failures = 0
        for score in [0, 0, 1, 1, 1, 0]:
            successes += score
            failures += 1 - score
            result = self.learner.update(result.state, assessment(score), [])
            self.assert_posterior(result, 1 + successes, 1 + failures, successes + failures)
            self.assertTrue(result.evidence_applied)
        self.assert_posterior(result, 4, 4, 6)

    def test_longer_sequence(self):
        scores = [1, 0, 1, 1] * 30
        result = self.learner.initial_state(["a"])
        for score in scores:
            result = self.learner.update(result.state, assessment(score), [])
            self.assertTrue(result.evidence_applied)
        self.assert_posterior(result, 91, 31, 120)

    def test_unclear_preserves_posterior_and_returns_independent_state(self):
        before = self.learner.update(self.learner.initial_state(["a", "b"]).state,
                                     assessment(1), [])
        result = self.learner.update(before.state, assessment(None), [])
        self.assertEqual(result.state, before.state)
        self.assertEqual(result.concepts, before.concepts)
        self.assertFalse(result.evidence_applied)
        self.assertIsNot(result.state, before.state)
        for concept_id in before.state.skills:
            self.assertIsNot(result.state.skills[concept_id], before.state.skills[concept_id])

    def test_concept_isolation(self):
        before = self.learner.initial_state(["z", "a", "b"])
        before = self.learner.update(before.state, assessment(0, "z"), [])
        result = self.learner.update(before.state, assessment(1), [])
        self.assertEqual([c.concept_id for c in result.concepts], ["z", "a", "b"])
        for concept_id in ["z", "b"]:
            self.assertEqual(result.state.skills[concept_id], before.state.skills[concept_id])
            self.assertEqual(next(c for c in result.concepts if c.concept_id == concept_id),
                             next(c for c in before.concepts if c.concept_id == concept_id))

    def test_input_immutability(self):
        state = self.learner.initial_state(["a", "b"]).state
        snapshot = state.model_dump()
        original_skills = dict(state.skills)
        result = self.learner.update(state, assessment(0), [])
        self.assertEqual(state.model_dump(), snapshot)
        self.assertIsNot(result.state, state)
        for concept_id, original in original_skills.items():
            self.assertIs(state.skills[concept_id], original)
            self.assertIsNot(result.state.skills[concept_id], original)
        result.state.skills["b"].alpha = 9
        self.assertEqual(state.model_dump(), snapshot)

    def test_history_independence(self):
        state = self.learner.initial_state(["a"]).state
        for score in [0, 1, None]:
            expected = self.learner.update(state, assessment(score), [])
            for length in [1, 2, 20]:
                with self.subTest(score=score, history_length=length):
                    history = [HistoryEntry(question_id="previous-question",
                                            evidence_applied=i % 2 == 0,
                                            candidate_id=None) for i in range(length)]
                    snapshot = [entry.model_dump() for entry in history]
                    self.assertEqual(self.learner.update(state, assessment(score), history), expected)
                    self.assertEqual([entry.model_dump() for entry in history], snapshot)

    def test_feedback_and_misconception_do_not_change_evidence(self):
        state = self.learner.initial_state(["a"]).state
        original = assessment(1)
        changed = original.model_copy(update={
            "feedback": "Different teaching text", "misconception_id": "some-diagnosis",
        })
        self.assertEqual(self.learner.update(state, original, []),
                         self.learner.update(state, changed, []))

    def test_contradictory_assessments(self):
        state = self.learner.initial_state(["a"]).state
        snapshot = state.model_dump()
        for outcome, score in [("correct", 0), ("correct", None), ("incorrect", 1),
                               ("incorrect", None), ("unclear", 0), ("unclear", 1)]:
            with self.subTest(outcome=outcome, score=score):
                invalid = Assessment(outcome=outcome, score=score, concept_id="a",
                                     misconception_id=None, feedback="Contradiction")
                with self.assertRaisesRegex(ValueError, "Contradictory assessment.*requires score"):
                    self.learner.update(state, invalid, [])
                self.assertEqual(state.model_dump(), snapshot)

    def test_unknown_concept_including_unclear(self):
        for score in [0, 1, None]:
            with self.subTest(score=score):
                with self.assertRaisesRegex(ValueError, "Unknown concept 'missing'"):
                    self.learner.update(self.learner.initial_state(["a"]).state,
                                        assessment(score, "missing"), [])

    def test_invalid_state_including_unrelated_concepts_and_unclear(self):
        invalid_skills = [
            SkillState(alpha=0, beta=2, evidence_count=0),
            SkillState(alpha=2, beta=0, evidence_count=0),
            SkillState(alpha=1, beta=1, evidence_count=-1),
            SkillState(alpha=2, beta=2, evidence_count=0),
        ]
        for invalid in invalid_skills:
            for concept_id in ["a", "b"]:
                for score in [1, None]:
                    with self.subTest(skill=invalid, concept_id=concept_id, score=score):
                        state = self.learner.initial_state(["a", "b"]).state
                        state.skills[concept_id] = invalid
                        snapshot = state.model_dump()
                        with self.assertRaisesRegex(ValueError, f"Invalid state for concept '{concept_id}'"):
                            self.learner.update(state, assessment(score), [])
                        self.assertEqual(state.model_dump(), snapshot)

    def test_duplicate_initial_concept_ids(self):
        with self.assertRaisesRegex(ValueError, "Duplicate initial concept IDs"):
            self.learner.initial_state(["a", "b", "a"])

    def test_estimates_use_parameters_not_just_evidence_count(self):
        state = LearnerState(skills={
            "a": SkillState(alpha=1, beta=3, evidence_count=2),
            "b": SkillState(alpha=3, beta=1, evidence_count=2),
        })
        result = self.learner.update(state, assessment(None), [])
        low, high = result.concepts
        self.assertEqual((low.mean, high.mean), (0.25, 0.75))
        self.assertEqual(low.interval90.lower, round(1 - 0.95 ** (1 / 3), 4))
        self.assertEqual(low.interval90.upper, round(1 - 0.05 ** (1 / 3), 4))
        self.assertEqual(high.interval90.lower, round(0.05 ** (1 / 3), 4))
        self.assertEqual(high.interval90.upper, round(0.95 ** (1 / 3), 4))


class BetaNumericalTests(unittest.TestCase):
    def test_cdf_endpoints_and_analytic_forms(self):
        for alpha, beta, cdf in [
            (1, 1, lambda x: x),
            (1, 2, lambda x: 2 * x - x * x),
            (2, 1, lambda x: x * x),
            (2, 2, lambda x: 3 * x * x - 2 * x ** 3),
        ]:
            self.assertEqual(_beta_cdf(0, alpha, beta), 0)
            self.assertEqual(_beta_cdf(1, alpha, beta), 1)
            for x in [0.001, 0.05, 0.25, 0.5, 0.95, 0.999]:
                with self.subTest(alpha=alpha, beta=beta, x=x):
                    self.assertAlmostEqual(_beta_cdf(x, alpha, beta), cdf(x), delta=1e-13)

    def test_known_quantiles_without_public_rounding(self):
        for probability in [0.05, 0.95]:
            for alpha, beta, expected in [
                (1, 1, probability),
                (1, 2, 1 - math.sqrt(1 - probability)),
                (2, 1, math.sqrt(probability)),
                # Invert 3*x**2 - 2*x**3 using its trigonometric closed form.
                (2, 2, 0.5 - math.sin(math.asin(1 - 2 * probability) / 3)),
            ]:
                with self.subTest(alpha=alpha, beta=beta, probability=probability):
                    self.assertAlmostEqual(_beta_quantile(probability, alpha, beta),
                                           expected, delta=1e-12)

    def test_large_binomial_coefficients_do_not_overflow(self):
        # C(1199, 600) is too large for a float, but symmetry gives this exact CDF.
        self.assertAlmostEqual(_beta_cdf(0.5, 600, 600), 0.5, delta=1e-11)


if __name__ == "__main__":
    unittest.main()
