"""Generic rich-pool protocol: exact-source tasks, no subject or filename rules."""
import copy
import json
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend.app.agents.provider import ProviderResult
from backend.app.ingestion.models import IngestionError, SourceChunk, SourceMaterial, normalized
from backend.app.ingestion.passages import build_passages, topic_passages, resolve_fixed_topics
from backend.app.ingestion.pipeline import process_course, _inspect_plan


TEXT = ("Resonators\nA resonator stores oscillating energy. "
        "Damping dissipates stored energy as heat. "
        "A stronger damping force reduces vibration amplitude. "
        "An external periodic force can sustain oscillations.")
MATERIAL = SourceMaterial("material_generic_fixture", "unrelated-notes.pptx", "hash", "pptx",
    (SourceChunk("chunk_generic_fixture", "slide", 1, TEXT, normalized(TEXT), "extracted"),),
    "extracted", ())


def proposal(passages):
    return {f"topic_{ci + 1}_question_{qi + 1}": {
        "assigned_answer_echo": p.answer_for_slot(qi),
        "prompt": p.completion_prompt(qi),
        "wrong_option_1": "All motion creates unlimited energy spontaneously.",
        "wrong_option_2": "Heat always turns directly into perfect perpetual motion.",
        "wrong_option_3": "The mechanism removes all physical interactions."
    } for ci, p in enumerate(passages) for qi in range(2 + len(p.extra_evidence))}


class GenericSourceCompletionTests(unittest.IsolatedAsyncioTestCase):
    async def test_unrelated_unnumbered_source_and_renamed_file_use_same_protocol(self):
        passages = topic_passages(build_passages((MATERIAL,)))
        self.assertEqual(len(passages), 1)
        self.assertEqual(len(set(a for _, a in passages[0].answers)), 4)
        requests = []
        async def complete(prompt, **kwargs):
            requests.append((json.loads(prompt), kwargs["response_schema"]))
            return ProviderResult(json.dumps(proposal(passages)), "bedrock", "test", 0)
        for filename in ("unrelated-notes.pptx", "totally-renamed.pdf"):
            with patch.dict("os.environ", {"MODEL_PROVIDER": "bedrock"}), patch(
                "backend.app.ingestion.pipeline.extract_material", return_value=replace(MATERIAL, filename=filename)), patch(
                "backend.app.ingestion.pipeline.provider.complete", side_effect=complete):
                course = await process_course(["unused-path"], title="Any title")
            self.assertEqual(len(course.questions), 4)
            self.assertEqual(course.metadata.provider_calls, 1)
            self.assertEqual(course.metadata.schema_version, "2")
            self.assertTrue(all(q.explanation in normalized(TEXT) for q in course.questions))
            self.assertTrue(all("Source recall:" in q.prompt for q in course.questions))
            for q in course.questions:
                key = next(c.text for c in q.choices if c.id == q.answer_key)
                self.assertNotIn(key, q.prompt)
                self.assertNotEqual(key, passages[0].answers[0][1])
        self.assertEqual(requests[0], requests[1])

    def test_changed_stem_key_and_source_alternative_rejected_independently(self):
        passages = topic_passages(build_passages((MATERIAL,)))
        base = proposal(passages)
        for field, value, reason in (
            ("prompt", "What does a resonator do?", "source_mismatch"),
            ("assigned_answer_echo", "A fabricated answer.", "invalid_answer_reference"),
            ("wrong_option_1", passages[0].answer_for_slot(1), "ambiguous_question"),
        ):
            data = copy.deepcopy(base)
            data["topic_1_question_1"][field] = value
            plan = resolve_fixed_topics(data, passages)
            artifacts, failures, accepted = _inspect_plan(plan, passages, (MATERIAL,), "generic_course")
            self.assertEqual(len(artifacts[1]), 3)
            self.assertTrue(any(f["reason"] == reason for f in failures))
            self.assertNotIn("/concepts/0/first_question", accepted)

    async def test_insufficient_pool_rejects_after_single_failed_fill(self):
        passages = topic_passages(build_passages((MATERIAL,)))
        data = proposal(passages)
        for key in ("topic_1_question_1", "topic_1_question_2"):
            data[key]["prompt"] = "An unbound application question?"
        complete = AsyncMock(side_effect=[
            ProviderResult(json.dumps(data), "bedrock", "test", 0),
            ProviderResult('{"repairs":[]}', "bedrock", "test", 0)])
        with patch.dict("os.environ", {"MODEL_PROVIDER": "bedrock"}), patch(
            "backend.app.ingestion.pipeline.extract_material", return_value=MATERIAL), patch(
            "backend.app.ingestion.pipeline.provider.complete", complete):
            with self.assertRaisesRegex(IngestionError, "fewer than three"):
                await process_course(["unused-path"])
        self.assertEqual(complete.await_count, 2)

    def test_production_has_no_demo_subject_or_recipe_dependency(self):
        production = Path(__file__).parents[2] / "app" / "ingestion"
        combined = "\n".join(p.read_text().casefold() for p in production.glob("*.py"))
        for forbidden in ("calculus", "derivative", "power rule", "product rule", "chain rule",
                          "grounded_recipes", "source_recipe", "safe_wording"):
            self.assertNotIn(forbidden, combined)
