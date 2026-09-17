import asyncio
import copy
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from backend.app.agents.provider import ProviderError, ProviderResult
from backend.app.ingestion import IngestionError, extract_material, process_course
from backend.app.ingestion.extraction import P, R
from backend.app.ingestion.pipeline import _local_proposal, validate_proposal
from backend.app.ingestion.passages import (apply_repairs, build_passages, resolve_plan,
                                           FORBIDDEN_STEM_WORDS, REPAIR_SYSTEM, SYSTEM)
from backend.tests.ingestion.helpers import plan_for


FIXTURES = Path(__file__).parent / "fixtures"


def edited_pptx(path, edit):
    with ZipFile(FIXTURES / "course.pptx") as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    edit(entries)
    with ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)


class ExtractionTests(unittest.TestCase):
    def test_pdf_real_compressed_fixture_and_blank_page(self):
        material = extract_material(FIXTURES / "course.pdf")
        self.assertEqual(material.filename, "course.pdf")
        self.assertEqual(material.format, "pdf")
        self.assertEqual(material.status, "partial")
        self.assertEqual([chunk.number for chunk in material.chunks], [1, 2, 3])
        self.assertEqual([chunk.location_kind for chunk in material.chunks], ["page"] * 3)
        self.assertIn("increasing depth", material.chunks[0].text)
        self.assertIn("lowest accumulated path cost", material.chunks[2].text)
        self.assertEqual(material.chunks[1].status, "empty")
        self.assertEqual(material.chunks[1].normalized_text, "")
        self.assertIn("\n", material.chunks[0].text)
        self.assertNotIn("\n", material.chunks[0].normalized_text)
        self.assertEqual(material.sha256, hashlib.sha256((FIXTURES / "course.pdf").read_bytes()).hexdigest())

    def test_pptx_fixture_and_blank_slide(self):
        material = extract_material(FIXTURES / "course.pptx")
        self.assertEqual(material.filename, "course.pptx")
        self.assertEqual([chunk.number for chunk in material.chunks], [1, 2, 3])
        self.assertEqual([chunk.location_kind for chunk in material.chunks], ["slide"] * 3)
        self.assertIn("never overestimates", material.chunks[0].text)
        self.assertEqual(material.chunks[1].status, "empty")
        self.assertIn("triangle inequality", material.chunks[2].text)

    def test_slide_order_comes_from_presentation_not_filenames(self):
        def reorder(entries):
            root = ET.fromstring(entries["ppt/presentation.xml"])
            slides = root.find(f"{{{P}}}sldIdLst")
            slides[:] = list(reversed(list(slides)))
            entries["ppt/presentation.xml"] = ET.tostring(root)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "reordered.pptx"
            edited_pptx(path, reorder)
            material = extract_material(path)
        self.assertTrue(material.chunks[0].text.startswith("Consistency"))
        self.assertEqual(material.chunks[0].number, 1)
        self.assertTrue(material.chunks[2].text.startswith("Admissibility"))

    def test_broken_slide_keeps_original_position(self):
        for replacement in [b"broken XML", b'<!DOCTYPE x [<!ENTITY x "bad">]><x/>', None]:
            def break_slide(entries):
                if replacement is None:
                    del entries["ppt/slides/slide1.xml"]
                else:
                    entries["ppt/slides/slide1.xml"] = replacement
            with self.subTest(replacement=replacement), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "broken.pptx"
                edited_pptx(path, break_slide)
                material = extract_material(path)
                self.assertEqual(material.chunks[0].status, "unreadable")
                self.assertEqual(material.chunks[0].number, 1)
                self.assertEqual(material.chunks[2].number, 3)
                self.assertIn("triangle inequality", material.chunks[2].text)
                self.assertIn("slide_1_unreadable", material.issues)

    def test_external_and_traversing_slide_targets_are_not_followed(self):
        for target in ["https://example.com/source.xml", "../../other.xml"]:
            def alter(entries):
                key = "ppt/_rels/presentation.xml.rels"
                root = ET.fromstring(entries[key])
                for relation in root:
                    if relation.get("Type") == R + "/slide":
                        relation.set("Target", target)
                entries[key] = ET.tostring(root)
            with self.subTest(target=target), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "external.pptx"
                edited_pptx(path, alter)
                material = extract_material(path)
                self.assertTrue(all(c.status == "unreadable" for c in material.chunks))

    def test_corrupt_files_have_no_invented_page_or_slide(self):
        with tempfile.TemporaryDirectory() as directory:
            for suffix in ["pdf", "pptx"]:
                path = Path(directory) / f"broken.{suffix}"
                path.write_bytes(b"not a document")
                material = extract_material(path)
                self.assertEqual(material.status, "unreadable")
                self.assertEqual(material.chunks, ())
                self.assertTrue(material.issues)

    def test_pdf_page_failure_keeps_other_pages_and_numbering(self):
        results = [subprocess.CompletedProcess([], 0, b"Pages: 3\n", b""),
                   subprocess.CompletedProcess([], 0, b"First page readable", b""),
                   subprocess.TimeoutExpired("pdftotext", 15),
                   subprocess.CompletedProcess([], 0, b"Third page readable", b"")]
        with patch("backend.app.ingestion.extraction._run", side_effect=results):
            material = extract_material(FIXTURES / "course.pdf")
        self.assertEqual([c.status for c in material.chunks], ["extracted", "unreadable", "extracted"])
        self.assertEqual(material.chunks[2].number, 3)
        self.assertIn("page_2_unreadable", material.issues)

    def test_missing_poppler_is_actionable_never_installed(self):
        with patch("backend.app.ingestion.extraction.shutil.which", return_value=None):
            with self.assertRaisesRegex(IngestionError, "Poppler"):
                extract_material(FIXTURES / "course.pdf")

    def test_stable_source_ids_and_source_bytes_unchanged(self):
        path = FIXTURES / "course.pptx"
        before = path.read_bytes()
        first, second = extract_material(path), extract_material(path)
        self.assertEqual(first, second)
        self.assertEqual(before, path.read_bytes())
        self.assertEqual(len({c.chunk_id for c in first.chunks}), len(first.chunks))
        with self.assertRaises(FrozenInstanceError):
            first.chunks[0].text = "altered"

    def test_unsupported_and_missing_file(self):
        for path in ["unsupported.txt", "missing.pdf"]:
            with self.assertRaises(IngestionError):
                extract_material(path)


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.materials = (extract_material(FIXTURES / "course.pptx"),)
        self.proposal = _local_proposal(self.materials)

    def validate(self, proposal=None):
        return validate_proposal(json.dumps(self.proposal if proposal is None else proposal), self.materials, "course_test")

    def test_valid_grounded_contract_and_server_only_answer_keys(self):
        concepts, questions = self.validate()
        self.assertEqual(len(questions), max(5, 2 * len(concepts)))
        lookup = {c.chunk_id: c for m in self.materials for c in m.chunks}
        for question in questions:
            self.assertIn(question.concept_id, {c.concept_id for c in concepts})
            answer = next(c.text for c in question.choices if c.id == question.answer_key)
            self.assertTrue(any(answer in ref.quote for ref in question.source_refs))
            for ref in question.source_refs:
                self.assertIn(ref.quote, lookup[ref.chunk_id].normalized_text)
            self.assertEqual(set(question.public()), {"question_id", "concept_id", "prompt", "choices"})

    def test_strict_json_and_duplicate_object_keys(self):
        for raw in ["", "not JSON", "```json\n{}\n```", "{} garbage", "[]", '{"concepts":[],"concepts":[]}',
                    '{"concepts":NaN}', '{"concepts":Infinity}', '{"concepts":' + '9' * 5000 + '}',
                    json.dumps({"concepts": []}),
                    json.dumps({"concepts": self.proposal["concepts"], "filename": "invented.pdf"})]:
            with self.subTest(raw=raw[:80]), self.assertRaises(IngestionError):
                validate_proposal(raw, self.materials, "course_test")

    def test_duplicate_concepts_and_proposed_ids_rejected(self):
        self.proposal["concepts"].append(copy.deepcopy(self.proposal["concepts"][0]))
        with self.assertRaisesRegex(IngestionError, "Duplicate concept"):
            self.validate()
        self.proposal["concepts"].pop()
        for key in ["concept_id", "filename", "page_number", "slide_number"]:
            value = copy.deepcopy(self.proposal)
            value["concepts"][0][key] = "untrusted"
            with self.subTest(key=key), self.assertRaises(IngestionError):
                self.validate(value)

    def test_unknown_empty_and_fabricated_source_references(self):
        blank_id = self.materials[0].chunks[1].chunk_id
        for update in [{"chunk_id": "invented"}, {"chunk_id": blank_id}, {"quote": "not present in sources"},
                       {"filename": "invented.pdf"}, {"page": 98}]:
            value = copy.deepcopy(self.proposal)
            value["concepts"][0]["source_refs"][0].update(update)
            with self.subTest(update=update), self.assertRaises(IngestionError):
                self.validate(value)

    def test_unrelated_concept_and_summary_rejected(self):
        for key in ["name", "summary"]:
            value = copy.deepcopy(self.proposal)
            value["concepts"][0][key] = "Unrelated marine biology"
            with self.subTest(key=key), self.assertRaises(IngestionError):
                self.validate(value)

    def test_invalid_questions_rejected(self):
        for update in [{"prompt": ""}, {"prompt": "Unrelated topic question?"}, {"choices": []},
                       {"choices": ["same", "SAME"]}, {"answer_index": True}, {"answer_index": "0"},
                       {"answer_index": 9}, {"explanation": "Fabricated explanation"},
                       {"answer_index": 1}, {"question_id": "duplicate-id"}, {"source_refs": []}]:
            value = copy.deepcopy(self.proposal)
            value["concepts"][0]["questions"][0].update(update)
            with self.subTest(update=update), self.assertRaises(IngestionError):
                self.validate(value)

    def test_duplicate_and_empty_questions_rejected(self):
        value = copy.deepcopy(self.proposal)
        value["concepts"][0]["questions"] = []
        with self.assertRaises(IngestionError):
            self.validate(value)
        value["concepts"][0]["questions"] = [self.proposal["concepts"][0]["questions"][0]] * 2
        with self.assertRaisesRegex(IngestionError, "Duplicate question"):
            self.validate(value)

    def test_shared_prompt_with_distinct_choices_is_not_a_duplicate(self):
        questions = self.proposal["concepts"][0]["questions"]
        questions[1]["prompt"] = questions[0]["prompt"]
        _, validated = self.validate()
        self.assertEqual(validated[0].prompt, validated[1].prompt)
        self.assertNotEqual(validated[0].choices, validated[1].choices)
        self.assertNotEqual(validated[0].question_id, validated[1].question_id)

    def test_duplicate_choices_cannot_be_disguised_by_order_case_or_whitespace(self):
        first = self.proposal["concepts"][0]["questions"][0]
        duplicate = copy.deepcopy(first)
        duplicate["prompt"] = "  " + first["prompt"].upper().replace(" ", "\n ")
        duplicate["choices"] = list(reversed(first["choices"]))
        duplicate["answer_index"] = len(first["choices"]) - 1 - first["answer_index"]
        # Keep the source-verbatim correct answer; vary only a distractor.
        duplicate["choices"][0] = "  " + duplicate["choices"][0].upper().replace(" ", "\n ")
        self.proposal["concepts"][0]["questions"][1] = duplicate
        with self.assertRaisesRegex(IngestionError, "Duplicate question"):
            self.validate()

    def test_evidence_must_intersect_concept_sources(self):
        value = copy.deepcopy(self.proposal)
        value["concepts"][0]["questions"][0]["source_refs"] = value["concepts"][1]["source_refs"]
        with self.assertRaisesRegex(IngestionError, "intersect"):
            self.validate(value)

    def test_answer_evidence_cannot_be_smuggled_in_from_an_unrelated_chunk(self):
        value = copy.deepcopy(self.proposal)
        question = value["concepts"][0]["questions"][0]
        unrelated = value["concepts"][1]["source_refs"][0]
        question["source_refs"] = [question["source_refs"][0], unrelated]
        question["choices"][0] = unrelated["quote"]
        question["explanation"] = unrelated["quote"]
        with self.assertRaisesRegex(IngestionError, "shared source evidence"):
            self.validate(value)

    def test_multiple_source_supported_choices_are_rejected(self):
        value = copy.deepcopy(self.proposal)
        question = value["concepts"][0]["questions"][0]
        question["choices"][1] = "never overestimates"
        with self.assertRaisesRegex(IngestionError, "ambiguous"):
            self.validate(value)

    def test_validation_does_not_mutate_sources_and_ids_are_stable(self):
        before = copy.deepcopy(self.materials)
        first, second = self.validate(), self.validate()
        self.assertEqual(first, second)
        self.assertEqual(self.materials, before)
        reversed_proposal = copy.deepcopy(self.proposal)
        reversed_proposal["concepts"].reverse()
        reordered = self.validate(reversed_proposal)
        self.assertEqual({c.concept_id for c in first[0]}, {c.concept_id for c in reordered[0]})
        self.assertEqual({q.question_id for q in first[1]}, {q.question_id for q in reordered[1]})


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"MODEL_PROVIDER": "fake"})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.call = AsyncMock()
        mock = patch("backend.app.ingestion.pipeline.provider.complete", self.call)
        mock.start()
        self.addCleanup(mock.stop)
        self.paths = [FIXTURES / "course.pdf", FIXTURES / "course.pptx"]

    async def test_local_and_fake_are_identical_deterministic_and_offline(self):
        first = await process_course(self.paths, mode="local", title="Graph search")
        second = await process_course(self.paths, mode="fake", title="Graph search")
        self.assertEqual(first, second)
        self.assertEqual((len(first.concepts), len(first.questions)), (4, 8))
        self.assertEqual(first.metadata.mode, "local")
        self.assertEqual(first.metadata.provider_calls, 0)
        self.assertTrue(first.metadata.requires_review)
        self.assertNotIn("fake provider echo", json.dumps(first.to_dict()))
        self.call.assert_not_awaited()

    async def test_bedrock_reuses_provider_once_and_returns_validated_course(self):
        materials = tuple(extract_material(path) for path in self.paths)
        self.call.return_value = ProviderResult(json.dumps(plan_for(materials)), "bedrock", "mock", 0)
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
            result = await process_course(self.paths)
        self.call.assert_awaited_once()
        self.assertEqual(result.metadata.mode, "bedrock")
        self.assertEqual(result.metadata.provider_calls, 1)
        self.assertEqual(result.materials, materials)
        payload = json.loads(self.call.call_args.args[0])
        self.assertTrue(all(set(source) == {"passage_id", "label", "text", "question_answers"} for source in payload["passages"]))
        self.assertNotIn("course.pdf", self.call.call_args.args[0])

    async def test_provider_errors_and_malformed_output_raise_without_retry_or_fallback(self):
        for failure in [ProviderError("private raw error"), "broken JSON", "{}", '{"concepts":[]}']:
            self.call.reset_mock()
            self.call.side_effect = failure if isinstance(failure, Exception) else None
            self.call.return_value = ProviderResult(str(failure), "bedrock", "mock", 0)
            with self.subTest(failure=str(failure)), patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
                with self.assertRaises(IngestionError) as caught:
                    await process_course(self.paths)
                self.assertEqual(len(caught.exception.materials), 2)
                self.assertNotIn("private raw error", str(caught.exception))
                self.call.assert_awaited_once()

    async def test_duplicate_bank_gets_one_validated_revision(self):
        materials = tuple(extract_material(path) for path in self.paths)
        valid = plan_for(materials)
        duplicate = copy.deepcopy(valid)
        duplicate["concepts"][0]["additional_questions"].append(duplicate["concepts"][0]["first_question"].copy())
        target = "/concepts/0/additional_questions/0"
        replacement = {**duplicate["concepts"][0]["first_question"],
                       "prompt": "Which statement explains how breadth-first search orders node expansion?"}
        repairs = {"repairs": [{"question_id": target, "question": replacement}]}
        self.call.side_effect = [ProviderResult(json.dumps(p), "bedrock", "mock", 0)
                                 for p in (duplicate, repairs)]
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
            course = await process_course(self.paths)
        self.assertEqual(self.call.await_count, 2)
        self.assertEqual(course.metadata.provider_calls, 2)
        revised = json.loads(self.call.call_args.args[0])
        self.assertEqual(revised["rejected_plan"], duplicate)
        self.assertEqual(revised["revision"], {"repair_targets": [target], "failures": [{
            "question_id": target, "reason": "duplicate_question_content",
            "duplicate_of": "/concepts/0/first_question"}]})
        self.assertEqual(self.call.call_args.kwargs["system"], REPAIR_SYSTEM)
        repair_items = self.call.call_args.kwargs["response_schema"]["properties"]["repairs"]["items"]
        self.assertEqual(repair_items["properties"]["question_id"]["enum"], [target])
        self.assertEqual(len(course.questions), sum(2 + len(c["additional_questions"]) for c in duplicate["concepts"]))
        expected = copy.deepcopy(duplicate)
        expected["concepts"][0]["additional_questions"][0] = replacement
        self.assertEqual(apply_repairs(duplicate, repairs, [target]), expected)
        # All existing question IDs/content and source records survive the repair.
        _, untouched = validate_proposal(json.dumps(resolve_plan(valid, build_passages(materials))), materials, course.course_id)
        self.assertTrue(set(untouched).issubset(set(course.questions)))
        self.assertEqual(course.materials, materials)

    async def test_ambiguous_question_gets_one_validated_targeted_repair(self):
        materials = tuple(extract_material(path) for path in self.paths)
        valid = plan_for(materials)
        ambiguous = copy.deepcopy(valid)
        ambiguous["concepts"][0]["second_question"]["wrong_option_2"] = "frontier of nodes"
        target = "/concepts/0/second_question"
        repairs = {"repairs": [{"question_id": target, "question": valid["concepts"][0]["second_question"]}]}
        self.call.side_effect = [ProviderResult(json.dumps(p), "bedrock", "mock", 0)
                                 for p in (ambiguous, repairs)]
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
            course = await process_course(self.paths)
        self.assertEqual(self.call.await_count, 2)
        revision = json.loads(self.call.call_args.args[0])["revision"]
        self.assertEqual(revision, {"repair_targets": [target], "failures": [{
            "question_id": target, "reason": "ambiguous_question", "field": "wrong_option_2",
            "rule": "wrong_option_is_substring_of_evidence"}]})
        expected = validate_proposal(json.dumps(resolve_plan(valid, build_passages(materials))), materials, course.course_id)
        self.assertEqual((course.concepts, course.questions), expected)

    async def test_one_revision_collects_negative_duplicate_and_ambiguity_failures(self):
        materials = tuple(extract_material(path) for path in self.paths)
        plan = plan_for(materials)
        plan["concepts"][0]["additional_questions"].append(copy.deepcopy(plan["concepts"][0]["first_question"]))
        valid_second = copy.deepcopy(plan["concepts"][0]["second_question"])
        plan["concepts"][0]["second_question"]["wrong_option_2"] = "frontier of nodes"
        valid_other = copy.deepcopy(plan["concepts"][1]["first_question"])
        plan["concepts"][1]["first_question"]["prompt"] = "Which explanation corrects this misunderstanding?"
        repairs = {"repairs": [
            {"question_id": "/concepts/1/first_question", "question": valid_other},
            {"question_id": "/concepts/0/second_question", "question": valid_second},
            {"question_id": "/concepts/0/additional_questions/0", "question": {
                **plan["concepts"][0]["first_question"],
                "prompt": "Which statement describes the node expansion order of breadth-first search?"}}]}
        self.call.side_effect = [ProviderResult(json.dumps(p), "bedrock", "mock", 0) for p in (plan, repairs)]
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
            course = await process_course(self.paths)
        failures = json.loads(self.call.call_args.args[0])["revision"]["failures"]
        self.assertEqual({f["reason"] for f in failures},
                         {"negative_question", "duplicate_question_content", "ambiguous_question"})
        self.assertEqual(course.metadata.provider_calls, 2)

    async def test_revision_is_bounded_and_still_rejects_invalid_content(self):
        materials = tuple(extract_material(path) for path in self.paths)
        duplicate = plan_for(materials)
        duplicate["concepts"][0]["additional_questions"].append(duplicate["concepts"][0]["first_question"].copy())
        target = "/concepts/0/additional_questions/0"
        original = duplicate["concepts"][0]["first_question"]
        ambiguous = {**original, "prompt": "Which claim describes the search frontier?", "wrong_option_1": "search"}
        unsupported = {**original, "answer_id": "invented"}
        for question, error in ((original, "Duplicate question"), (ambiguous, "ambiguous"),
                                (unsupported, "unexpected fields")):
            self.call.reset_mock()
            revision = {"repairs": [{"question_id": target, "question": question}]}
            self.call.side_effect = [ProviderResult(json.dumps(p), "bedrock", "mock", 0)
                                     for p in (duplicate, revision)]
            with self.subTest(error=error), patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
                course = await process_course(self.paths)
                self.assertTrue(course.metadata.degraded)
                self.assertEqual(course.metadata.discarded_question_count, 1)
                self.assertEqual(course.metadata.repaired_question_count, 0)
                self.assertEqual(len(course.questions), 8)
            self.assertEqual(self.call.await_count, 2)

    async def test_ambiguity_remaining_after_revision_is_omitted(self):
        materials = tuple(extract_material(path) for path in self.paths)
        plan = plan_for(materials)
        question = plan["concepts"][0]["second_question"]
        question["wrong_option_2"] = "frontier of nodes"
        repairs = {"repairs": [{"question_id": "/concepts/0/second_question", "question": question}]}
        self.call.side_effect = [ProviderResult(json.dumps(p), "bedrock", "mock", 0) for p in (plan, repairs)]
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
            course = await process_course(self.paths)
        self.assertEqual(len(course.questions), 7)
        self.assertTrue(course.metadata.degraded)
        self.assertFalse(any(c.text == "frontier of nodes" for q in course.questions for c in q.choices))
        self.assertEqual(self.call.await_count, 2)

    async def test_negative_stem_repair_preserves_slot_and_source(self):
        materials = tuple(extract_material(path) for path in self.paths)
        valid = plan_for(materials)
        plan = copy.deepcopy(valid)
        plan["concepts"][0]["first_question"]["prompt"] = "Which statement is a common misconception?"
        target = "/concepts/0/first_question"
        repairs = {"repairs": [{"question_id": target, "question": valid["concepts"][0]["first_question"]}]}
        self.call.side_effect = [ProviderResult(json.dumps(p), "bedrock", "mock", 0) for p in (plan, repairs)]
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
            course = await process_course(self.paths)
        revision = json.loads(self.call.call_args.args[0])["revision"]
        self.assertEqual(revision["failures"], [{"question_id": target, "reason": "negative_question", "field": "prompt",
                                               "rule": "forbidden_whole_word_in_prompt",
                                               "matched_keywords": ["misconception"]}])
        expected = validate_proposal(json.dumps(resolve_plan(valid, build_passages(materials))), materials, course.course_id)
        self.assertEqual((course.concepts, course.questions), expected)
        self.assertEqual(self.call.await_count, 2)

    async def test_positive_rewording_with_forbidden_keyword_is_still_rejected_and_diagnosed(self):
        materials = tuple(extract_material(path) for path in self.paths)
        plan = plan_for(materials)
        plan["concepts"][0]["first_question"]["prompt"] = "Which statement is a common misconception?"
        repair = {**plan["concepts"][0]["first_question"],
                  "prompt": "Which accurate statement corrects this misunderstanding?"}
        response = {"repairs": [{"question_id": "/concepts/0/first_question", "question": repair}]}
        self.call.side_effect = [ProviderResult(json.dumps(p), "bedrock", "mock", 0) for p in (plan, response)]
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}), \
                self.assertLogs("uvicorn.error.ingestion", level="INFO") as logs:
            course = await process_course(self.paths)
        self.assertTrue(course.metadata.degraded)
        self.assertFalse(any("misunderstanding" in q.prompt for q in course.questions))
        self.assertEqual(self.call.await_count, 2)
        logged = "\n".join(logs.output)
        self.assertIn("attempt=2 question=/concepts/0/first_question reason=negative_question keywords=misunderstanding", logged)
        self.assertNotIn(repair["prompt"], logged)
        self.assertNotIn(build_passages(materials)[0].text, logged)

    def test_repair_cannot_replace_valid_questions_or_provenance(self):
        materials = tuple(extract_material(path) for path in self.paths)
        plan = plan_for(materials)
        before = copy.deepcopy(plan)
        target = "/concepts/0/first_question"
        repair = {"question_id": target, "question": plan["concepts"][0]["first_question"]}
        cases = [plan, {"repairs": []}, {"repairs": [repair, repair]},
                 {"repairs": [{**repair, "question_id": "/concepts/0/second_question"}]},
                 {"repairs": [{**repair, "question_id": "/concepts/0/passage_id"}]}]
        for response in cases:
            with self.subTest(response=response), self.assertRaises(IngestionError):
                apply_repairs(plan, response, [target])
            self.assertEqual(plan, before)
        with self.assertRaises(IngestionError):
            apply_repairs(plan, {"repairs": [repair, repair]}, [target, "/concepts/0/second_question"])
        patched = apply_repairs(plan, {"repairs": [{**repair, "question": {
            **repair["question"], "source_refs": []}}]}, [target])
        with self.assertRaises(IngestionError):
            resolve_plan(patched, build_passages(materials))

    def test_generation_and_repair_require_objective_unique_questions(self):
        for prompt in (SYSTEM, REPAIR_SYSTEM):
            self.assertIn("exactly one objectively correct answer", prompt)
            self.assertIn("distinct and non-equivalent", prompt)
            self.assertIn("never repeat", prompt)
            self.assertIn("same question semantics", prompt)
            self.assertIn("literal keyword rule", prompt)
            self.assertIn(", ".join(FORBIDDEN_STEM_WORDS), prompt)

    async def test_revision_cannot_extend_overall_generation_deadline(self):
        materials = tuple(extract_material(path) for path in self.paths)
        duplicate = plan_for(materials)
        duplicate["concepts"][0]["additional_questions"].append(duplicate["concepts"][0]["first_question"].copy())
        async def respond(*args, **kwargs):
            if self.call.await_count == 1:
                return ProviderResult(json.dumps(duplicate), "bedrock", "mock", 0)
            await asyncio.Event().wait()
        self.call.side_effect = respond
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}), \
                patch("backend.app.ingestion.pipeline.GENERATION_BUDGET_SECONDS", .05):
            course = await process_course(self.paths)
        self.assertTrue(course.metadata.degraded)
        self.assertEqual(course.metadata.discarded_question_count, 1)
        self.assertEqual(self.call.await_count, 2)

    async def test_bedrock_does_not_accept_fake_provider_echo(self):
        self.call.return_value = ProviderResult("[fake provider echo] secret", "fake", "fake", 0)
        with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
            with self.assertRaisesRegex(IngestionError, "Unexpected provider"):
                await process_course(self.paths)
        self.call.assert_awaited_once()

    async def test_empty_and_unreadable_input_error_retains_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.pptx"
            def blank(entries):
                for key in entries:
                    if key.startswith("ppt/slides/slide") and key.endswith(".xml"):
                        entries[key] = f'<p:sld xmlns:p="{P}"/>'.encode()
            edited_pptx(path, blank)
            for data in [None, b"corrupt archive"]:
                if data is not None:
                    path.write_bytes(data)
                with self.assertRaisesRegex(IngestionError, "No extractable text") as caught:
                    await process_course([path])
                self.assertEqual(len(caught.exception.materials), 1)
        self.call.assert_not_awaited()

    async def test_limits_and_configuration_rejected_before_provider(self):
        for paths, mode in [([], "local"), (self.paths * 5, "local"), (self.paths, "unknown"),
                            (self.paths, "bedrock"), ([self.paths[0]] * 2, "local")]:
            with self.subTest(paths=paths, mode=mode), self.assertRaises(IngestionError):
                await process_course(paths, mode=mode)
        self.call.assert_not_awaited()

    async def test_large_context_is_rejected_without_truncation_or_call(self):
        material = extract_material(FIXTURES / "course.pptx")
        large = replace(material.chunks[0], text="word " * 6000, normalized_text="word " * 6000)
        with patch("backend.app.ingestion.pipeline.extract_material", return_value=replace(material, chunks=(large,))):
            with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
                with self.assertRaisesRegex(IngestionError, "24,000"):
                    await process_course([self.paths[0]])
        self.call.assert_not_awaited()

    async def test_source_files_not_mutated_by_pipeline(self):
        before = [path.read_bytes() for path in self.paths]
        await process_course(self.paths)
        self.assertEqual([path.read_bytes() for path in self.paths], before)


class CliTests(unittest.TestCase):
    def test_local_cli_writes_server_artifact_and_errors_cleanly(self):
        result = subprocess.run([sys.executable, "-m", "backend.app.ingestion", str(FIXTURES / "course.pptx")],
                                capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        self.assertEqual(len(data["concepts"]), 2)
        self.assertIn("answer_key", data["questions"][0])
        error = subprocess.run([sys.executable, "-m", "backend.app.ingestion", "bad.txt"],
                               capture_output=True, text=True)
        self.assertEqual(error.returncode, 1)
        self.assertEqual(error.stdout, "")
        self.assertNotIn("Traceback", error.stderr)


if __name__ == "__main__":
    unittest.main()
