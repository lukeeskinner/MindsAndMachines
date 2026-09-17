"""Private registry/adapter checks using the actual local ingestion artifact."""
import asyncio
from dataclasses import replace
from pathlib import Path
import unittest

from backend.app.ingestion import process_course
from backend.app.storage.courses import MemoryCourseRegistry, adapt_question
from backend.app.teaching.catalog import Catalog


class CourseRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = Path(__file__).resolve().parents[1] / "ingestion/fixtures/course.pptx"
        cls.course = asyncio.run(process_course([fixture], title="Course one", mode="local"))
        cls.other = asyncio.run(process_course([fixture], title="Course two", mode="local"))

    def setUp(self):
        self.registry = MemoryCourseRegistry()
        self.registry.register(self.course)

    def test_register_and_lookup_preserve_full_private_artifact(self):
        self.assertEqual(self.registry.register(self.course), self.course.course_id)
        self.assertIs(self.registry.get(self.course.course_id), self.course)
        self.assertEqual(self.registry.get(self.course.course_id).to_dict(), self.course.to_dict())
        self.assertTrue(self.course.questions[0].answer_key)
        self.assertTrue(self.course.materials[0].chunks[0].text)

    def test_unknown_course_does_not_fall_back(self):
        for lookup in (self.registry.get, self.registry.catalog):
            with self.assertRaises(KeyError):
                lookup("missing")

    def test_registry_instances_are_isolated(self):
        with self.assertRaises(KeyError):
            MemoryCourseRegistry().get(self.course.course_id)

    def test_same_id_cannot_replace_an_artifact(self):
        changed = replace(self.course, questions=(replace(self.course.questions[0],
                          explanation="Different private explanation"), *self.course.questions[1:]))
        with self.assertRaises(ValueError):
            self.registry.register(changed)
        self.assertIs(self.registry.get(self.course.course_id), self.course)

    def test_empty_artifact_is_rejected(self):
        for changed in (replace(self.course, course_id=""), replace(self.course, concepts=()),
                        replace(self.course, questions=())):
            with self.assertRaises(ValueError):
                self.registry.register(changed)

    def test_metadata_is_an_explicit_public_projection(self):
        metadata = self.registry.catalog(self.course.course_id).public_metadata()
        self.assertEqual(metadata.model_dump(), {
            "course_id": self.course.course_id, "title": "Course one",
            "concepts": [{"concept_id": c.concept_id, "display_name": c.name}
                         for c in self.course.concepts],
            "source_filenames": ["course.pptx"], "question_count": len(self.course.questions),
        })
        for private_field in ("answer_key", "rubric", "explanation", "source_refs", "quote",
                              "normalized_text", "summary", "warnings", "metadata"):
            self.assertNotIn(f'"{private_field}"', metadata.model_dump_json())
        metadata.concepts[0].display_name = "Changed public copy"
        self.assertEqual(self.registry.get(self.course.course_id).concepts, self.course.concepts)

    def test_adapter_maps_all_fields_and_retains_provenance(self):
        source = self.course.questions[0]
        adapted = adapt_question(source)
        self.assertEqual(adapted.question.model_dump(), {
            "question_id": source.question_id, "concept_id": source.concept_id,
            "prompt": source.prompt, "choices": [{"id": c.id, "text": c.text} for c in source.choices],
            "answer_key": source.answer_key, "rubric": source.explanation, "review": False,
        })
        self.assertEqual(adapted.source_refs, source.source_refs)
        for ref in adapted.source_refs:
            material, chunk = next((m, c) for m in self.course.materials for c in m.chunks
                                   if c.chunk_id == ref.chunk_id)
            self.assertIn(ref.quote, chunk.normalized_text)
            self.assertEqual(material.filename, "course.pptx")
            self.assertEqual(chunk.location_kind, "slide")
            self.assertGreater(chunk.number, 0)
        public = adapted.question.public().model_dump()
        self.assertEqual(set(public), {"question_id", "concept_id", "prompt", "choices", "review"})
        self.assertEqual(public["choices"], [{"id": c.id, "text": c.text} for c in source.choices])
        self.assertNotIn("unsure", [choice["id"] for choice in public["choices"]])

    def test_multiple_courses_and_question_copies_stay_isolated(self):
        self.registry.register(self.other)
        first = self.registry.catalog(self.course.course_id)
        second = self.registry.catalog(self.other.course_id)
        self.assertEqual(first.concept_ids, [c.concept_id for c in self.course.concepts])
        self.assertTrue(set(first.concept_ids).isdisjoint(second.concept_ids))
        with self.assertRaises(KeyError):
            second.question(first.first_question_id)
        changed = first.question(first.first_question_id)
        changed.question.rubric = "Changed runtime copy"
        changed.question.choices[0].text = "Changed choice"
        self.assertEqual(first.question(first.first_question_id).question.rubric,
                         self.course.questions[0].explanation)
        self.assertEqual(first.question(first.first_question_id).question.choices[0].text,
                         self.course.questions[0].choices[0].text)

    def test_demo_catalog_is_untouched(self):
        demo = Catalog()
        before = {key: question.model_dump() for key, question in demo.questions.items()}
        self.registry.register(self.other)
        view = self.registry.catalog(self.other.course_id)
        view.question(view.first_question_id)
        self.assertEqual({key: question.model_dump() for key, question in demo.questions.items()}, before)
        self.assertEqual(Catalog().questions, demo.questions)
