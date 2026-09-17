import asyncio
import copy
from dataclasses import replace
from pathlib import Path
import os
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.agents.coordinator import Coordinator
from backend.app.agents.real_assessor import RealAssessor
from backend.app.ingestion import IngestionError, process_course
from backend.app.ingestion.models import (
    Choice, Concept, ProcessedCourse, ProcessingMetadata, Question,
    SourceChunk, SourceMaterial, SourceReference, TeachingArtifact,
)
from backend.app.ingestion.teaching import PROCESS_TEMPLATES
from backend.app.learner.bayesian import BayesianLearner
from backend.app.policy.adaptive import AdaptivePolicy
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.runtime_catalog import build_runtime_catalog
from backend.app.teaching.tutor import Tutor
from contracts.models import Assessment, Decision, HistoryEntry, LearnerPresentationPreferences, TurnRequest


def synthetic_course():
    # This legitimate course sentence is forbidden by the demo's topic check.
    fact = "Breadth-first search explores nodes in order of increasing depth."
    text = fact + " A queue stores waiting nodes. The waiting nodes form a frontier."
    chunk = SourceChunk("source-synthetic", "page", 1, text, text, "extracted")
    refs = (SourceReference(chunk.chunk_id, text),)
    material = SourceMaterial("material-synthetic", "synthetic.pdf", "digest", "pdf", (chunk,), "extracted", ())
    concept = Concept("concept-synthetic", "Breadth-first search", fact, refs)
    questions = tuple(Question(
        f"synthetic-q{i}", concept.concept_id, f"Recall item {i} about the source.",
        (Choice("a", answer), Choice("b", "unrelated")), "a", rubric, refs,
    ) for i, (answer, rubric) in enumerate((("queue", "A queue stores waiting nodes."),
                                           ("frontier", "The waiting nodes form a frontier.")), 1))
    teaching = tuple(TeachingArtifact(
        f"synthetic-teaching-{kind}", concept.concept_id, kind,
        (fact, *paragraphs), refs,
    ) for kind, paragraphs in PROCESS_TEMPLATES.items())
    return ProcessedCourse("course-synthetic", "Graph reading", (material,), (concept,), questions,
                           ProcessingMetadata("1", "local", 0, ()), teaching)


class RuntimeCatalogTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        fixtures = Path(__file__).resolve().parents[1] / "ingestion/fixtures"
        cls.course = asyncio.run(process_course([fixtures / "course.pdf", fixtures / "course.pptx"], mode="local"))

    def setUp(self):
        self.catalog = build_runtime_catalog(self.course)
        self.estimates = BayesianLearner().initial_state(self.catalog.concept_ids).concepts
        self.assessment = Assessment(outcome="correct", concept_id=self.catalog.concept_ids[0],
                                     score=1, misconception_id=None, feedback="PRIVATE FEEDBACK")

    def test_concepts_questions_candidates_and_content_resolve(self):
        self.assertEqual(self.catalog.concepts, self.course.concepts)
        self.assertEqual(self.catalog.concept_ids, [c.concept_id for c in self.course.concepts])
        self.assertEqual(len(self.catalog.candidates), len(self.course.questions) * 3)
        ids = [c.candidate_id for c in self.catalog.candidates]
        self.assertEqual(len(set(ids)), len(ids))
        for candidate in self.catalog.candidates:
            self.assertEqual(self.catalog.question(candidate.next_question_id).concept_id, candidate.concept_id)
            self.assertEqual(set(self.catalog.teaching[candidate.content_id]),
                             {"standard", "plain", "concise", "plain_concise"})
            self.assertEqual(self.catalog.artifacts[candidate.content_id].kind, candidate.kind)
        self.assertEqual(self.catalog.candidates, build_runtime_catalog(self.course).candidates)

    def test_safe_questions_preserve_private_data_and_provenance(self):
        for source in self.course.questions:
            question = self.catalog.question(source.question_id)
            self.assertEqual(question.answer_key, source.answer_key)
            self.assertEqual(question.rubric, source.explanation)
            self.assertEqual(question.prompt, source.prompt)
            self.assertEqual([(c.id, c.text) for c in question.choices[:-1]], [(c.id, c.text) for c in source.choices])
            self.assertEqual(self.catalog.question_provenance[question.question_id], source.source_refs)
            self.assertEqual(question.choices[-1].id, "unsure")
            self.assertNotEqual(question.answer_key, "unsure")
            self.assertEqual(set(question.public().model_dump()), {"question_id", "concept_id", "prompt", "choices"})

    async def test_unsure_is_unscored_by_existing_assessor(self):
        with patch.dict(os.environ, {"MODEL_PROVIDER": "fake"}), patch(
            "backend.app.agents.provider.complete", new_callable=AsyncMock
        ) as complete:
            question = self.catalog.question(self.catalog.first_question_id)
            assessment = await RealAssessor().assess(question, "unsure")
        self.assertEqual((assessment.outcome, assessment.score), ("unclear", None))
        complete.assert_not_called()

    def test_reserved_choice_or_invalid_answer_is_rejected_without_mutation(self):
        source = self.course.questions[0]
        for question in (replace(source, answer_key="unsure"), replace(source, answer_key="missing"),
                         replace(source, choices=(*source.choices, Choice("unsure", "Something else")))):
            with self.assertRaises(IngestionError):
                build_runtime_catalog(replace(self.course, questions=(question, *self.course.questions[1:])))

    def test_current_questions_and_consumed_candidates_are_filtered(self):
        first = self.catalog.first_question_id
        available = self.catalog.eligible_candidates(current_question_id=first)
        self.assertEqual(len(available.candidates), 3)
        self.assertTrue(all(c.next_question_id != first for c in available.candidates))
        used = available.candidates[0].candidate_id
        filtered = self.catalog.eligible_candidates(current_question_id=first, consumed_candidate_ids=[used])
        self.assertEqual(len(filtered.candidates), 2)
        self.assertNotIn(used, {c.candidate_id for c in filtered.candidates})

    def test_concept_exhaustion_does_not_imply_course_completion(self):
        first = self.catalog.first_question_id
        second = self.catalog.eligible_candidates(current_question_id=first).candidates[0].next_question_id
        status = self.catalog.eligible_candidates(current_question_id=second, consumed_question_ids=[first])
        self.assertFalse(status.candidates)
        self.assertTrue(status.concept_exhausted)
        self.assertFalse(status.course_exhausted)
        self.assertEqual(status.next_concept_id, self.catalog.concept_ids[1])
        self.assertEqual(self.catalog.question(status.next_concept_question_id).concept_id, status.next_concept_id)

    def test_consumed_candidate_exhaustion_is_not_question_exhaustion(self):
        status = self.catalog.eligible_candidates(current_question_id=self.catalog.first_question_id,
                    consumed_candidate_ids=[c.candidate_id for c in self.catalog.candidates])
        self.assertFalse(status.candidates)
        self.assertFalse(status.concept_exhausted)
        self.assertFalse(status.course_exhausted)

    def test_unknown_and_cross_course_session_ids_are_rejected(self):
        with self.assertRaises(KeyError):
            self.catalog.eligible_candidates(current_question_id="missing")
        for kwargs in ({"consumed_question_ids": ["foreign"]}, {"consumed_candidate_ids": ["foreign"]}):
            with self.assertRaises(ValueError):
                self.catalog.eligible_candidates(current_question_id=self.catalog.first_question_id, **kwargs)

    async def test_all_kinds_render_provider_free_in_local_modes_and_every_preference(self):
        before = copy.deepcopy(self.course)
        for mode in ("fake", "local", "openai"):
            with patch.dict(os.environ, {"MODEL_PROVIDER": mode}), patch(
                "backend.app.agents.provider.complete", new_callable=AsyncMock
            ) as complete:
                for candidate in self.catalog.candidates[:6]:
                    decision = Decision(**candidate.model_dump(), reason="Test")
                    for mask in range(8):
                        prefs = LearnerPresentationPreferences(plain_language=bool(mask & 1),
                                  concise=bool(mask & 2), step_by_step=bool(mask & 4))
                        result = await Tutor(self.catalog).teach(decision, self.assessment, self.estimates, prefs)
                        self.assertEqual(result.next_question_id, candidate.next_question_id)
                        self.assertIn("Draft course guidance", result.text)
                        self.assertNotIn("PRIVATE FEEDBACK", result.text)
                        if prefs.step_by_step:
                            self.assertIn("1. ", result.text)
                complete.assert_not_called()
        self.assertEqual(self.course, before)

    async def test_synthetic_course_does_not_use_demo_topic_or_graph_rules(self):
        catalog = build_runtime_catalog(synthetic_course())
        estimates = BayesianLearner().initial_state(catalog.concept_ids).concepts
        assessment = self.assessment.model_copy(update={"concept_id": catalog.concept_ids[0]})
        with patch.dict(os.environ, {"MODEL_PROVIDER": "fake"}), patch(
            "backend.app.agents.provider.complete", new_callable=AsyncMock
        ) as complete:
            for candidate in catalog.candidates:
                result = await Tutor(catalog).teach(Decision(**candidate.model_dump(), reason="Test"),
                    assessment, estimates, LearnerPresentationPreferences())
                self.assertIn("Breadth-first search", result.text)
                self.assertFalse(result.fallback)
            complete.assert_not_called()

    async def test_trusted_decision_includes_next_question_and_rejects_tampering(self):
        candidate = self.catalog.candidates[0]
        decision = Decision(**candidate.model_dump(), reason="Test")
        for update in ({"next_question_id": None}, {"next_question_id": "foreign"},
                       {"content_id": "foreign"}, {"concept_id": "foreign"},
                       {"kind": "socratic_hint"}, {"candidate_id": "foreign"}):
            with self.subTest(update=update), self.assertRaises(ValueError):
                await Tutor(self.catalog).teach(decision.model_copy(update=update), self.assessment,
                                               self.estimates, LearnerPresentationPreferences())

    async def test_mutable_content_and_feedback_cannot_override_artifact(self):
        candidate = self.catalog.candidates[0]
        self.catalog.teaching[candidate.content_id]["standard"] = ["The answer is a."]
        self.catalog.candidates[0].next_question_id = "foreign"
        result = await Tutor(self.catalog).teach(Decision(**self.catalog._bindings[candidate.candidate_id], reason="Test"),
                    self.assessment, self.estimates, LearnerPresentationPreferences())
        self.assertNotIn("The answer is a", result.text)
        self.assertNotEqual(result.next_question_id, "foreign")

    async def test_local_unclear_output_is_deterministic_and_does_not_generate(self):
        decision = Decision(**self.catalog.candidates[0].model_dump(), reason="Test")
        unclear = self.assessment.model_copy(update={"outcome": "unclear", "score": None})
        tutor = Tutor(self.catalog)
        with patch.dict(os.environ, {"MODEL_PROVIDER": "fake"}), patch(
            "backend.app.agents.provider.complete", new_callable=AsyncMock
        ) as complete:
            first = await tutor.teach(decision, unclear, self.estimates, LearnerPresentationPreferences())
            second = await tutor.teach(decision, unclear, self.estimates, LearnerPresentationPreferences())
        self.assertEqual(first, second)
        self.assertTrue(first.fallback)
        complete.assert_not_called()

    def test_two_courses_instances_and_demo_remain_isolated(self):
        demo = Catalog()
        before = copy.deepcopy(vars(demo))
        original = copy.deepcopy(self.course)
        second = build_runtime_catalog(synthetic_course())
        another = build_runtime_catalog(self.course)
        self.catalog.questions[self.catalog.first_question_id].rubric = "Modified copy"
        self.catalog.teaching[self.course.teaching[0].teaching_id]["standard"].append("Modified copy")
        self.assertNotEqual(self.catalog.questions, another.questions)
        self.assertNotEqual(self.catalog.teaching, another.teaching)
        self.assertTrue(set(second.questions).isdisjoint(another.questions))
        self.assertTrue({c.candidate_id for c in second.candidates}.isdisjoint(c.candidate_id for c in another.candidates))
        with self.assertRaises(KeyError):
            second.question(another.first_question_id)
        self.assertEqual(self.course, original)
        self.assertEqual(vars(demo), before)
        self.assertEqual(vars(Catalog()), before)

    def test_legacy_missing_kind_duplicate_identity_and_ungrounded_content_fail(self):
        for teaching in ((), self.course.teaching[:-1], (*self.course.teaching, self.course.teaching[0]),
                         (replace(self.course.teaching[0], paragraphs=("Invented content.",)), *self.course.teaching[1:])):
            with self.assertRaises(IngestionError):
                build_runtime_catalog(replace(self.course, teaching=teaching))

    def test_display_notice_cannot_leak_a_short_correct_answer(self):
        course = synthetic_course()
        question = replace(course.questions[0], choices=(Choice("a", "Draft"), Choice("b", "Other")))
        with self.assertRaisesRegex(IngestionError, "correct-choice"):
            build_runtime_catalog(replace(course, questions=(question, *course.questions[1:])))

    async def test_finite_course_progression_through_unchanged_coordinator_and_policy(self):
        class AssessorStub:
            async def assess(self, question, answer):
                return Assessment(outcome="unclear", concept_id=question.concept_id, score=None,
                                  misconception_id=None, feedback="No evidence")

        learner = BayesianLearner()
        coordinator = Coordinator(AssessorStub(), learner, AdaptivePolicy(), Tutor(self.catalog))
        state = learner.initial_state(self.catalog.concept_ids).state
        history = []
        current = self.catalog.first_question_id
        seen = []
        with patch("backend.app.agents.provider.complete", new_callable=AsyncMock) as complete:
            for _ in range(len(self.catalog.questions)):
                self.assertNotIn(current, seen)
                available = self.catalog.eligible_candidates(current_question_id=current,
                    consumed_question_ids=[h.question_id for h in history],
                    consumed_candidate_ids=[h.candidate_id for h in history if h.candidate_id])
                update, response = await coordinator.run_turn(
                    TurnRequest(session_id="test", question_id=current, answer="unsure"),
                    self.catalog.question(current), state, history, list(available.candidates), self.catalog.questions)
                self.assertFalse(update.evidence_applied)
                history.append(HistoryEntry(question_id=current, evidence_applied=False,
                    candidate_id=response.decision.candidate_id if response.decision else None))
                seen.append(current)
                state = update.state
                if available.course_exhausted:
                    self.assertIsNone(response.next_question)
                    break
                current = (response.next_question.question_id if response.next_question
                           else available.next_concept_question_id)
                self.assertIsNotNone(current)
            complete.assert_not_called()
        self.assertEqual(set(seen), set(self.catalog.questions))
        self.assertTrue(available.course_exhausted)
        self.assertIsNone(available.next_concept_question_id)


if __name__ == "__main__":
    unittest.main()
