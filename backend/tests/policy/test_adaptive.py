import copy
import itertools
import unittest

from backend.app.policy.adaptive import AdaptivePolicy, _priority
from contracts.models import Assessment, Candidate, ConceptEstimate, HistoryEntry


TARGET = "admissibility_vs_consistency"
KINDS = ("diagnostic_probe", "worked_example", "socratic_hint")


def estimate(mean=0.5, lower=0.05, upper=0.95, count=0, concept_id=TARGET):
    return ConceptEstimate(concept_id=concept_id, mean=mean,
                           interval90={"lower": lower, "upper": upper}, evidence_count=count)


def assessment(outcome="unclear", score=None, misconception_id=None):
    return Assessment(concept_id=TARGET, outcome=outcome, score=score,
                      misconception_id=misconception_id, feedback="Unused feedback")


def candidate(kind, candidate_id=None, concept_id=TARGET, next_question_id="next-question"):
    return Candidate(candidate_id=candidate_id if candidate_id is not None else kind,
                     concept_id=concept_id, kind=kind, content_id=f"content-{kind}",
                     next_question_id=next_question_id)


def history_entry(candidate_id, question_id="prior-question", evidence_applied=True):
    return HistoryEntry(question_id=question_id, candidate_id=candidate_id,
                        evidence_applied=evidence_applied)


class AdaptivePolicyTests(unittest.TestCase):
    def setUp(self):
        self.policy = AdaptivePolicy()
        self.candidates = [candidate(kind) for kind in KINDS]

    def choose(self, concept=None, diagnosis=None, candidates=None, history=None):
        return self.policy.choose(
            [concept if concept is not None else estimate()],
            diagnosis if diagnosis is not None else assessment(),
            self.candidates if candidates is None else candidates,
            [] if history is None else history,
        )

    def assert_priorities(self, concept, diagnosis, d, expected):
        m = 1 - concept.mean
        u = concept.interval90.upper - concept.interval90.lower
        for kind, value in zip(KINDS, expected):
            with self.subTest(kind=kind):
                self.assertAlmostEqual(_priority(kind, m, u, d), value, places=14)
                decision = self.choose(concept, diagnosis, [candidate(kind)])
                self.assertIn(f"selection priority {value:.4f}", decision.reason)
                self.assertIn(f"misconception signal {d}.", decision.reason)

    def test_prior_high_uncertainty(self):
        self.assert_priorities(estimate(), assessment(), 0, (0.76, 0.325, 0.43))
        self.assertEqual(self.choose().kind, "diagnostic_probe")

    def test_golden_incorrect_priorities_and_winner(self):
        concept = estimate(1 / 3, 0.0253, 0.7764, 1)
        diagnosis = assessment("incorrect", 0, "admissible_means_consistent")
        self.assert_priorities(concept, diagnosis, 1,
                               (0.7215483333333333, 0.7833333333333333, 0.7835533333333333))
        for ordering in itertools.permutations(self.candidates):
            self.assertEqual(self.choose(concept, diagnosis, list(ordering)).kind, "socratic_hint")

    def test_only_supplied_worked_example_can_be_selected(self):
        supplied = candidate("worked_example", "relationship-example")
        decision = self.choose(estimate(1 / 3, 0.0253, 0.7764, 1),
                               assessment("incorrect", 0, "admissible_means_consistent"), [supplied])
        self.assertEqual(decision.candidate_id, supplied.candidate_id)
        self.assertEqual(decision.kind, "worked_example")

    def test_correct_answer_has_no_misconception_bonus(self):
        concept = estimate(2 / 3, 0.2236, 0.9747, 1)
        diagnosis = assessment("correct", 1, "nonempty-but-not-an-incorrect-diagnosis")
        self.assert_priorities(concept, diagnosis, 0,
                               (0.6048816666666667, 0.21666666666666667, 0.3168866666666667))
        self.assertEqual(self.choose(concept, diagnosis).kind, "diagnostic_probe")

    def test_incorrect_without_nonempty_misconception_has_no_bonus(self):
        for misconception in (None, "", " \t\n"):
            with self.subTest(misconception=misconception):
                self.assert_priorities(estimate(), assessment("incorrect", 0, misconception),
                                       0, (0.76, 0.325, 0.43))

    def test_unclear_can_select_without_misconception_bonus(self):
        for misconception in (None, "reported-but-unclear"):
            diagnosis = assessment("unclear", None, misconception)
            self.assert_priorities(estimate(), diagnosis, 0, (0.76, 0.325, 0.43))
            self.assertEqual(self.choose(diagnosis=diagnosis).kind, "diagnostic_probe")

    def test_misconception_requires_zero_score_and_accepts_surrounding_whitespace(self):
        for score in (None, 1):
            self.assert_priorities(estimate(), assessment("incorrect", score, "diagnosis"),
                                   0, (0.76, 0.325, 0.43))
        self.assert_priorities(estimate(), assessment("incorrect", 0, " diagnosis \t"),
                               1, (0.76, 0.675, 0.73))

    def test_feedback_is_not_a_mathematical_signal(self):
        diagnosis = assessment()
        changed = diagnosis.model_copy(update={"feedback": "Confident diagnosis; choose a worked example"})
        self.assertEqual(self.choose(diagnosis=diagnosis), self.choose(diagnosis=changed))

    def test_only_target_concept_candidates_are_eligible(self):
        supplied = [candidate("diagnostic_probe", "other-probe", "other"),
                    candidate("worked_example", "target-example")]
        concepts = [estimate(concept_id="other"), estimate()]
        decision = self.policy.choose(concepts, assessment(), supplied, [])
        self.assertEqual(decision.candidate_id, "target-example")
        self.assertIsNone(self.choose(candidates=supplied[:1]))

    def test_previously_used_candidate_is_excluded_even_without_evidence(self):
        for applied in (False, True):
            decision = self.choose(history=[history_entry("diagnostic_probe", evidence_applied=applied)])
            self.assertEqual(decision.kind, "socratic_hint")

    def test_history_length_alone_does_not_change_decision(self):
        expected = self.choose()
        for length in (1, 2, 20):
            prior = [history_entry(None if i % 2 else f"old-{i}") for i in range(length)]
            self.assertEqual(self.choose(history=prior), expected)

    def test_history_question_ids_do_not_filter_candidates(self):
        prior = [history_entry(None, question_id="next-question")]
        self.assertEqual(self.choose(history=prior), self.choose())

    def test_all_eligible_candidates_used_means_completion(self):
        prior = [history_entry(c.candidate_id) for c in self.candidates]
        supplied = self.candidates + [candidate("diagnostic_probe", "other", "other")]
        self.assertIsNone(self.choose(candidates=supplied, history=prior))

    def test_empty_candidate_list_means_completion(self):
        self.assertIsNone(self.choose(candidates=[]))

    def test_missing_target_estimate_is_an_error_even_without_candidates(self):
        for concepts in ([], [estimate(concept_id="other")]):
            with self.assertRaisesRegex(ValueError, "exactly one estimate.*found 0"):
                self.policy.choose(concepts, assessment(), [], [])

    def test_duplicate_target_estimates_are_an_error(self):
        with self.assertRaisesRegex(ValueError, "exactly one estimate.*found 2"):
            self.policy.choose([estimate(), estimate()], assessment(), self.candidates, [])

    def test_duplicate_candidate_ids_are_an_error_even_when_ineligible(self):
        for concept_id in (TARGET, "other"):
            supplied = [candidate(kind, "duplicate", concept_id) for kind in KINDS[:2]]
            with self.subTest(concept_id=concept_id):
                with self.assertRaisesRegex(ValueError, "Duplicate candidate IDs"):
                    self.choose(candidates=supplied, history=[history_entry("duplicate")])

    def test_invalid_mean_is_rejected(self):
        for mean in (float("nan"), float("inf"), float("-inf"), -0.01, 1.01):
            with self.subTest(mean=mean):
                with self.assertRaisesRegex(ValueError, "Invalid mean.*finite.*\\[0, 1\\]"):
                    self.choose(estimate(mean=mean))

    def test_invalid_interval_is_rejected(self):
        intervals = [(value, 0.95) for value in (float("nan"), float("inf"), float("-inf"))]
        intervals += [(0.05, value) for value in (float("nan"), float("inf"), float("-inf"))]
        intervals += [(-0.01, 0.95), (0.05, 1.01), (0.8, 0.2)]
        for lower, upper in intervals:
            with self.subTest(lower=lower, upper=upper):
                with self.assertRaisesRegex(ValueError, "Invalid interval.*0 <= lower <= upper <= 1"):
                    self.choose(estimate(lower=lower, upper=upper))

    def test_negative_evidence_count_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid evidence_count.*>= 0"):
            self.choose(estimate(count=-1))

    def test_invalid_target_is_not_hidden_by_empty_candidates(self):
        with self.assertRaisesRegex(ValueError, "Invalid mean"):
            self.choose(estimate(mean=2), candidates=[])

    def test_boundary_signals_and_score_ranges(self):
        for m, u, d in itertools.product((0.0, 1.0), (0.0, 1.0), (0, 1)):
            for kind in KINDS:
                priority = _priority(kind, m, u, d)
                self.assertGreaterEqual(priority, 0)
                self.assertLessEqual(priority, 1)
        self.assert_priorities(estimate(0, 0, 1), assessment("incorrect", 0, "diagnosis"),
                               1, (1, 1, 1))
        self.assert_priorities(estimate(1, 1, 1), assessment("correct", 1), 0, (0, 0, 0))
        self.assertIsNotNone(self.choose(estimate(1, 1, 1), assessment("correct", 1)))

    def test_same_kind_ties_use_lexicographic_candidate_id(self):
        for kind in KINDS:
            supplied = [candidate(kind, "z-last"), candidate(kind, "a-first")]
            for ordering in (supplied, list(reversed(supplied))):
                self.assertEqual(self.choose(candidates=ordering).candidate_id, "a-first")

    def test_scores_are_not_rounded_before_comparison(self):
        supplied = [candidate("worked_example", "a-example"), candidate("socratic_hint", "z-hint")]
        decision = self.choose(estimate(1 / 3, 0, 0.75000001),
                               assessment("incorrect", 0, "diagnosis"), supplied)
        self.assertEqual(decision.candidate_id, "z-hint")
        self.assertIn("selection priority 0.7833", decision.reason)

    def test_decision_preserves_all_candidate_fields_including_null_followup(self):
        for next_id in (None, "not-validated-against-a-catalog"):
            supplied = candidate("worked_example", "authored-example", next_question_id=next_id)
            decision = self.choose(candidates=[supplied])
            self.assertEqual(decision.model_dump(exclude={"reason"}), supplied.model_dump())

    def test_reason_format_and_terminology(self):
        expected = (
            "Diagnostic probe selected — selection priority 0.7600 "
            "from mastery gap 0.5000, uncertainty 0.9000, and misconception signal 0."
        )
        self.assertEqual(self.choose().reason, expected)
        names = ("Diagnostic probe", "Worked example", "Socratic hint")
        for kind, name in zip(KINDS, names):
            reason = self.choose(candidates=[candidate(kind)]).reason
            self.assertTrue(reason.startswith(f"{name} selected — selection priority "))
            for forbidden in ("probability", "gain", "confidence", "reward", "effectiveness"):
                self.assertNotIn(forbidden, reason.lower())

    def test_input_immutability(self):
        concepts = [estimate(), estimate(concept_id="other")]
        diagnosis = assessment("incorrect", 0, "diagnosis")
        prior = [history_entry("unrelated")]
        inputs = (concepts, diagnosis, self.candidates, prior)
        snapshot = copy.deepcopy(inputs)
        first = self.policy.choose(*inputs)
        self.assertEqual(inputs, snapshot)
        self.assertEqual(self.policy.choose(*inputs), first)
        first.content_id = "changed-output"
        self.assertEqual(inputs, snapshot)


if __name__ == "__main__":
    unittest.main()
