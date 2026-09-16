"""Check the production content, its answer keys, and its existing runtime seams."""
import itertools
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import AsyncMock, patch

from backend.app.agents.assessor import FakeAssessor
from backend.app.agents.provider import ProviderResult
from backend.app.policy.adaptive import AdaptivePolicy
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.tutor import Tutor
from contracts.models import (
    Assessment, ConceptEstimate, Decision, HistoryEntry, LearnerPresentationPreferences,
)


TARGET = "admissibility_vs_consistency"
KINDS = {"diagnostic_probe", "worked_example", "socratic_hint"}
VARIANTS = {"standard", "plain", "concise", "plain_concise"}
CONTENT = Path(__file__).resolve().parents[3] / "content" / "demo.json"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate catalog field: {key}")
        result[key] = value
    return result


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads(CONTENT.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        self.catalog = Catalog()

    def test_unique_ids_and_resolved_concept_content_question_links(self):
        self.assertEqual(set(self.catalog.concept_ids), {
            "bfs", "ucs", "astar", "admissibility", "consistency", TARGET})
        for records, field in ((self.data["questions"], "question_id"),
                               (self.data["candidates"], "candidate_id")):
            ids = [record[field] for record in records]
            self.assertTrue(all(ids))
            self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual({c.kind for c in self.catalog.candidates}, KINDS)
        followups = []
        for candidate in self.catalog.candidates:
            with self.subTest(candidate=candidate.candidate_id):
                self.assertEqual(candidate.concept_id, TARGET)
                self.assertIn(candidate.content_id, self.catalog.teaching)
                self.assertIn(candidate.next_question_id, self.catalog.questions)
                self.assertEqual(self.catalog.question(candidate.next_question_id).concept_id, TARGET)
                followups.append(candidate.next_question_id)
        # The policy filters used candidates, so distinct destinations provide freshness.
        self.assertEqual(len(followups), len(set(followups)))
        self.assertNotIn(self.catalog.first_question_id, followups)
        self.assertEqual(set(followups) | {self.catalog.first_question_id}, set(self.catalog.questions))

    def test_question_keys_are_unique_choices_and_private(self):
        prompts = []
        for question in self.catalog.questions.values():
            with self.subTest(question=question.question_id):
                self.assertEqual(question.concept_id, TARGET)
                ids = [choice.id for choice in question.choices]
                self.assertEqual(len(ids), len(set(ids)))
                self.assertEqual(len({c.text for c in question.choices}), len(ids))
                self.assertIn(question.answer_key, ids)
                self.assertNotEqual(question.answer_key, "unsure")
                self.assertTrue(question.rubric.strip())
                public = question.public().model_dump()
                self.assertNotIn("answer_key", public)
                self.assertNotIn("rubric", public)
                prompts.append(question.prompt)
        self.assertEqual(len(prompts), len(set(prompts)))

    def test_graph_answer_keys_match_shortest_paths_and_every_edge(self):
        classifications = {
            (True, True): "Both admissible and consistent.",
            (True, False): "Admissible, but not consistent.",
            (False, False): "Neither admissible nor consistent.",
        }
        for question_id in ("relationship-q02", "relationship-q03", "relationship-q04"):
            with self.subTest(question=question_id):
                question = self.catalog.question(question_id)
                edges = {(a, b): int(cost) for a, b, cost in re.findall(
                    r"([SAG]) \u2192 ([SAG]) \(cost (\d+)\)", question.prompt)}
                h = {node: int(value) for node, value in re.findall(r"h\(([SAG])\)=(\d+)", question.prompt)}
                self.assertEqual(set(edges), {("S", "A"), ("A", "G"), ("S", "G")})
                self.assertEqual(set(h), {"S", "A", "G"})
                self.assertEqual(h["G"], 0)
                remaining = {"G": 0, "A": edges["A", "G"],
                             "S": min(edges["S", "G"], edges["S", "A"] + edges["A", "G"])}
                admissible = all(h[node] <= cost for node, cost in remaining.items())
                consistent = all(h[a] <= cost + h[b] for (a, b), cost in edges.items())
                answer = next(c.text for c in question.choices if c.id == question.answer_key)
                self.assertEqual(answer, classifications[admissible, consistent])

    def test_all_presentation_variants_and_guidance_shape(self):
        for candidate in self.catalog.candidates:
            content = self.catalog.teaching[candidate.content_id]
            self.assertEqual(set(content), VARIANTS)
            for variant, paragraphs in content.items():
                with self.subTest(candidate=candidate.candidate_id, variant=variant):
                    self.assertIsInstance(paragraphs, list)
                    self.assertTrue(paragraphs)
                    self.assertTrue(all(isinstance(p, str) and p.strip() for p in paragraphs))
                    text = " ".join(paragraphs)
                    if candidate.kind != "worked_example":
                        self.assertIn("?", text)
                        self.assertNotRegex(text, r"\d|answer key|[<>]=?|therefore")
                        question = self.catalog.question(candidate.next_question_id)
                        for choice in question.choices:
                            if choice.id == question.answer_key:
                                self.assertNotIn(choice.text, text)
                    if candidate.kind == "socratic_hint":
                        self.assertLessEqual(len(text), 360)
                    if variant.startswith("plain"):
                        self.assertNotRegex(text, r"\b[hc]\(")

    def test_existing_policy_can_choose_each_kind_without_score_changes(self):
        # Actual score regimes: uncertainty -> probe; weak diagnosed performance ->
        # example; the original first wrong answer -> hint (a narrow score lead).
        fixtures = [
            (0.5, 0.05, 0.95, 0, "unclear", None, None, "diagnostic_probe"),
            (0.2, 0.05, 0.45, 5, "incorrect", 0, "admissible_means_consistent", "worked_example"),
            (1 / 3, 0.0253, 0.7764, 1, "incorrect", 0, "admissible_means_consistent", "socratic_hint"),
        ]
        for mean, lower, upper, count, outcome, score, misconception, expected in fixtures:
            with self.subTest(kind=expected):
                concept = ConceptEstimate(concept_id=TARGET, mean=mean,
                    interval90={"lower": lower, "upper": upper}, evidence_count=count)
                assessment = Assessment(concept_id=TARGET, outcome=outcome, score=score,
                    misconception_id=misconception, feedback="")
                policy = AdaptivePolicy()
                decision = policy.choose([concept], assessment, self.catalog.candidates, [])
                self.assertEqual(decision.kind, expected)
                history = [HistoryEntry(question_id=self.catalog.first_question_id,
                    candidate_id=c.candidate_id, evidence_applied=False) for c in self.catalog.candidates]
                self.assertIsNone(policy.choose([concept], assessment, self.catalog.candidates, history))
                for candidate in self.catalog.candidates:
                    others_used = [h for h in history if h.candidate_id != candidate.candidate_id]
                    self.assertEqual(policy.choose([concept], assessment, self.catalog.candidates,
                                                   others_used).candidate_id, candidate.candidate_id)


class CatalogTutorTests(unittest.IsolatedAsyncioTestCase):
    async def test_each_choice_uses_its_server_side_key(self):
        for question in Catalog().questions.values():
            for choice in question.choices:
                with self.subTest(question=question.question_id, choice=choice.id):
                    result = await FakeAssessor().assess(question, choice.id)
                    expected = None if choice.id == "unsure" else int(choice.id == question.answer_key)
                    self.assertEqual(result.score, expected)

    async def test_every_authored_variant_resolves_locally_and_passes_tutor_validation(self):
        catalog = Catalog()
        tutor = Tutor(catalog)
        assessment = Assessment(concept_id=TARGET, outcome="incorrect", score=0,
            misconception_id="admissible_means_consistent", feedback="Revisit the distinction.")
        concepts = [ConceptEstimate(concept_id=TARGET, mean=1 / 3,
            interval90={"lower": 0.0253, "upper": 0.7764}, evidence_count=1)]
        for candidate, plain, concise, steps in itertools.product(
                catalog.candidates, (False, True), (False, True), (False, True)):
            with self.subTest(candidate=candidate.candidate_id, plain=plain, concise=concise, steps=steps):
                prefs = LearnerPresentationPreferences(plain_language=plain, concise=concise, step_by_step=steps)
                variant = "plain_concise" if plain and concise else "plain" if plain else "concise" if concise else "standard"
                paragraphs = catalog.teaching[candidate.content_id][variant]
                expected = "\n".join(f"{i}. {p}" for i, p in enumerate(paragraphs, 1)) if steps else "\n\n".join(paragraphs)
                decision = Decision(**candidate.model_dump(), reason="Catalog verification")
                with patch("backend.app.teaching.tutor.provider.complete", new_callable=AsyncMock) as complete:
                    with patch.dict(os.environ, {"MODEL_PROVIDER": "fake"}):
                        result = await tutor.teach(decision, assessment, concepts, prefs)
                        self.assertEqual(result.text, expected)
                        self.assertEqual(result.teaching_source, "authored")
                        self.assertEqual(result.next_question_id, candidate.next_question_id)
                        complete.assert_not_called()
                    complete.return_value = ProviderResult(json.dumps({"text": expected}), "bedrock", "test", 0)
                    with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
                        result = await tutor.teach(decision, assessment, concepts, prefs)
                        self.assertFalse(result.fallback)
                        self.assertEqual(result.teaching_source, "bedrock")
                        self.assertEqual(result.text, expected)
                        self.assertEqual(result.next_question_id, candidate.next_question_id)
                        complete.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
