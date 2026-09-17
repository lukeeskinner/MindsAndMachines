"""HTTP upload boundary with real local extraction and mocked provider failures."""
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import httpx

from backend.app.agents.provider import ProviderError, ProviderResult
from backend.app.api import courses
from backend.app.ingestion import IngestionError, extract_material
from backend.app.ingestion.extraction import MAX_FILE_BYTES
from backend.app.ingestion.pipeline import _local_proposal
from backend.app import main
from backend.app.main import create_app
from backend.app.storage.courses import MemoryCourseRegistry
from backend.app.teaching.catalog import Catalog
from backend.app.teaching.runtime_catalog import build_runtime_catalog


FIXTURES = Path(__file__).resolve().parents[2] / "backend/tests/ingestion/fixtures"


def upload(name="course.pptx", data=None):
    return ("files", (name, data if data is not None else (FIXTURES / name).read_bytes(),
                       "application/octet-stream"))


def upload_app(registry):
    return create_app(course_registry=registry)


class CourseUploadTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {"MODEL_PROVIDER": "fake", "DYNAMODB_TABLE_NAME": "",
                                     "COGNITO_USER_POOL_ID": "", "COGNITO_APP_CLIENT_ID": ""})
        env.start()
        self.addCleanup(env.stop)
        self.provider = AsyncMock(side_effect=AssertionError("No live provider calls"))
        patcher = patch("backend.app.ingestion.pipeline.provider.complete", self.provider)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.registry = MemoryCourseRegistry()
        self.client = TestClient(upload_app(self.registry))

    def test_pdf_upload_registered_and_public(self):
        self.assert_upload("course.pdf")

    def test_pptx_upload_registered_and_public(self):
        self.assert_upload("course.pptx")

    def test_default_app_mounts_upload_and_sessions_with_one_private_registry(self):
        with patch.object(main, "MemoryCourseRegistry", wraps=MemoryCourseRegistry) as factory:
            app = create_app()
        factory.assert_called_once_with()
        matches = [route for route in app.routes
                   if getattr(route, "path", None) == "/api/v1/courses" and "POST" in route.methods]
        self.assertEqual(len(matches), 1)
        client = TestClient(app)
        response = client.post("/api/v1/courses", files=[upload()])
        self.assertEqual(response.status_code, 201, response.text)
        course_id = response.json()["course_id"]
        preview = client.post("/api/v1/sessions", json={"course_id": course_id})
        self.assertEqual(preview.status_code, 201, preview.text)
        self.assertEqual(preview.json()["course_id"], course_id)
        isolated = TestClient(create_app()).post("/api/v1/sessions", json={"course_id": course_id})
        self.assertEqual(isolated.status_code, 404)

    def assert_upload(self, name):
        result = self.client.post("/api/v1/courses", files=[upload(name)], data={"title": "My course"})
        self.assertEqual(result.status_code, 201, result.text)
        data = result.json()
        course = self.registry.get(data["course_id"])
        self.assertEqual(len(course.teaching), 3 * len(course.concepts))
        self.assertEqual({item.kind for item in course.teaching},
                         {"diagnostic_probe", "worked_example", "socratic_hint"})
        runtime = build_runtime_catalog(course)
        self.assertIs(runtime.course, course)
        self.assertTrue(runtime.candidates)
        self.assertEqual(data, self.registry.catalog(course.course_id).public_metadata().model_dump())
        self.assertEqual(set(data), {"course_id", "title", "concepts", "source_filenames", "question_count"})
        self.assertTrue(all(set(c) == {"concept_id", "display_name"} for c in data["concepts"]))
        self.assertEqual(data["source_filenames"], [name])
        for private in ("answer_key", "rubric", "explanation", "source_refs", "quote", "summary",
                        "materials", "metadata", "warnings", "normalized_text", "SYSTEM",
                        "teaching", "teaching_id", "paragraphs", "requires_review"):
            self.assertNotIn(f'"{private}"', result.text)
        for question in course.questions:
            self.assertTrue(question.answer_key)
            self.assertNotIn(question.explanation, result.text)
        self.provider.assert_not_called()
        preview = self.client.post("/api/v1/sessions", json={"course_id": course.course_id})
        self.assertEqual(preview.status_code, 201)
        body = preview.json()
        turn = self.client.post("/api/v1/turns", json={"session_id": body["session_id"],
                                "question_id": body["question"]["question_id"], "answer": "a"})
        self.assertEqual(turn.status_code, 409)

    def test_single_generation_preserves_teaching_and_rejects_invalid_teaching(self):
        materials = (extract_material(FIXTURES / "course.pptx"),)
        proposal = _local_proposal(materials)
        for valid in (True, False):
            if not valid:
                proposal["concepts"][0]["teaching"][0]["paragraphs"] = ["Unsupported private teaching"]
            self.provider.reset_mock()
            self.provider.side_effect = None
            self.provider.return_value = ProviderResult(json.dumps(proposal), "bedrock", "mock", 0)
            with patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
                result = self.client.post("/api/v1/courses", files=[upload()])
            self.assertEqual(result.status_code, 201 if valid else 422, result.text)
            self.provider.assert_awaited_once()
            self.assertNotIn("teaching", result.text)
            if valid:
                stored = self.registry.get(result.json()["course_id"])
                self.assertEqual(stored.metadata.provider_calls, 1)
                self.assertEqual(len(stored.teaching), 3 * len(stored.concepts))
                self.assertTrue(build_runtime_catalog(stored).candidates)
            else:
                self.assertEqual(list(self.registry._courses.values()), [stored])

    def test_multi_file_and_original_names(self):
        files = [upload("Lecture notes.PDF", (FIXTURES / "course.pdf").read_bytes()),
                 upload("My slides.pptx", (FIXTURES / "course.pptx").read_bytes())]
        result = self.client.post("/api/v1/courses", files=files)
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(result.json()["source_filenames"], ["Lecture notes.PDF", "My slides.pptx"])
        self.assertEqual(result.json()["title"], "Uploaded course")

    def test_duplicate_stable_id_is_idempotent_but_replacement_conflicts(self):
        first = self.client.post("/api/v1/courses", files=[upload()])
        second = self.client.post("/api/v1/courses", files=[upload()])
        self.assertEqual(first.status_code, 201)
        self.assertEqual(first.json(), second.json())
        original = self.registry.get(first.json()["course_id"])
        changed = replace(original, questions=(replace(original.questions[0], explanation="private changed"),
                                               *original.questions[1:]))
        with patch.object(courses, "process_course", AsyncMock(return_value=changed)):
            response = self.client.post("/api/v1/courses", files=[upload()])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.registry.get(original.course_id), original)

    def test_unsupported_extensions_and_unsafe_names(self):
        for name, status in [("secret.txt", 415), ("course.pdf.exe", 415), ("file", 415),
                             ("../course.pdf", 422), ("folder/course.pdf", 422),
                             ("folder\\course.pdf", 422), ("x" * 256 + ".pdf", 422)]:
            with self.subTest(name=name), patch.object(courses, "process_course", AsyncMock()) as process:
                result = self.client.post("/api/v1/courses", files=[upload(name, b"bad")])
                self.assertEqual(result.status_code, status, result.text)
                self.assertNotIn('"' + name + '"', result.text)
                process.assert_not_called()

    def test_legacy_windows_filename_is_reduced_to_its_original_basename(self):
        result = self.client.post("/api/v1/courses", files=[
            upload("C:\\temp\\course.pptx", (FIXTURES / "course.pptx").read_bytes())])
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(result.json()["source_filenames"], ["course.pptx"])

    def test_too_many_files_missing_files_invalid_fields_and_title(self):
        requests = [dict(files=[upload()] * 9), dict(data={"title": "x"}),
                    dict(files=[upload()], data={"title": " "}),
                    dict(files=[upload()], data={"title": "x" * 201}),
                    dict(files=[upload()], data={"mode": "bedrock"}),
                    dict(files=[("wrong", ("course.pptx", b"bad"))]),
                    dict(files=[upload(), ("title", ("title.txt", b"secret"))])]
        for kwargs in requests:
            with self.subTest(keys=list(kwargs)), patch.object(courses, "process_course", AsyncMock()) as process:
                response = self.client.post("/api/v1/courses", **kwargs)
                self.assertIn(response.status_code, (415, 422), response.text)
                process.assert_not_called()

    def test_oversized_input_is_rejected_before_processing(self):
        with patch.object(courses, "process_course", AsyncMock()) as process:
            response = self.client.post("/api/v1/courses", files=[upload("large.pdf", b"x" * (MAX_FILE_BYTES + 1))])
        self.assertEqual(response.status_code, 413)
        process.assert_not_called()

    def test_corrupt_empty_and_duplicate_material_fail_validation(self):
        for files in ([upload("broken.pptx", b"bad")], [upload("empty.pptx", b"")], [upload()] * 2):
            with self.subTest(count=len(files)):
                result = self.client.post("/api/v1/courses", files=files)
                self.assertEqual(result.status_code, 422, result.text)
        self.assertEqual(self.registry._courses, {})

    def test_poppler_unavailable_is_controlled(self):
        with patch("backend.app.ingestion.extraction.shutil.which", return_value=None):
            result = self.client.post("/api/v1/courses", files=[upload("course.pdf")])
        self.assertEqual(result.status_code, 503)
        self.assertIn("Poppler", result.json()["detail"])

    def test_provider_failure_timeout_and_malformed_generation(self):
        error = ProviderError("private credentials prompt and source")
        timeout = ProviderError("private timeout details")
        timeout.__cause__ = TimeoutError("private socket details")
        for failure, status in [(error, 502), (timeout, 504), (None, 422)]:
            self.provider.reset_mock()
            self.provider.side_effect = failure
            self.provider.return_value = ProviderResult("private malformed JSON", "bedrock", "mock", 0)
            with self.subTest(status=status), patch.dict(os.environ, {"MODEL_PROVIDER": "bedrock"}):
                response = self.client.post("/api/v1/courses", files=[upload()])
            self.assertEqual(response.status_code, status, response.text)
            self.assertNotIn("private", response.text)
            self.assertNotIn("Traceback", response.text)
            self.provider.assert_awaited_once()
            self.assertEqual(self.registry._courses, {})

    def test_failure_messages_never_echo_exception_or_materials(self):
        for failure, status in [(IngestionError("private source prompt credential"), 422),
                                (RuntimeError("private stack"), 500)]:
            with patch.object(courses, "process_course", AsyncMock(side_effect=failure)):
                response = self.client.post("/api/v1/courses", files=[upload()])
            self.assertEqual(response.status_code, status)
            self.assertNotIn("private", response.text)
            self.assertEqual(self.registry._courses, {})

    def test_staging_and_parser_temporary_files_cleaned_on_success_and_failure(self):
        original_process = courses.process_course
        original_stage = courses._stage_files
        paths, streams = [], []

        def capture(files, directory):
            streams.extend(file.file for file in files)
            staged = original_stage(files, directory)
            paths.extend(staged)
            self.assertTrue(all(path.exists() for path in staged))
            return staged

        for failure in (None, IngestionError("private failure")):
            with tempfile.TemporaryDirectory() as root:
                original_temporary = tempfile.TemporaryDirectory
                with patch.object(courses.tempfile, "TemporaryDirectory",
                                  side_effect=lambda **kw: original_temporary(dir=root, **kw)), \
                        patch.object(courses, "_stage_files", side_effect=capture), \
                        patch.object(courses, "process_course",
                                     AsyncMock(side_effect=failure or original_process)):
                    response = self.client.post("/api/v1/courses", files=[upload()])
                self.assertEqual(response.status_code, 422 if failure else 201, response.text)
                self.assertEqual(list(Path(root).iterdir()), [])
        self.assertTrue(all(not path.exists() for path in paths))
        self.assertTrue(all(stream.closed for stream in streams))

    def test_parser_spools_close_on_oversize_and_incomplete_body(self):
        from starlette import formparsers
        real_spool = formparsers.SpooledTemporaryFile
        opened = []

        def capture(**kw):
            stream = real_spool(**kw)
            opened.append(stream)
            return stream

        with patch.object(formparsers, "SpooledTemporaryFile", side_effect=capture), \
                patch.object(courses, "MAX_FILE_BYTES", 10):
            oversized = self.client.post("/api/v1/courses", files=[upload("large.pdf", b"x" * 11)])
            incomplete = self.client.post("/api/v1/courses", content=(
                b'--boundary\r\nContent-Disposition: form-data; name="files"; filename="x.pdf"\r\n\r\na'),
                headers={"content-type": "multipart/form-data; boundary=boundary"})
        self.assertEqual(oversized.status_code, 413)
        self.assertEqual(incomplete.status_code, 422)
        self.assertTrue(opened)
        self.assertTrue(all(stream.closed for stream in opened))

    def test_demo_behavior_unchanged(self):
        before = {key: value.model_dump() for key, value in Catalog().questions.items()}
        self.assertEqual(self.client.post("/api/v1/courses", files=[upload()]).status_code, 201)
        demo = self.client.post("/api/v1/sessions", json={}).json()
        self.assertIsNone(demo["course_id"])
        response = self.client.post("/api/v1/turns", json={"session_id": demo["session_id"],
                                   "question_id": demo["question"]["question_id"], "answer": "a"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(before, {key: value.model_dump() for key, value in Catalog().questions.items()})


class UploadConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancellation_waits_for_file_workers_before_cleanup(self):
        loop = asyncio.get_running_loop()
        for phase in ("staging", "extraction"):
            started = asyncio.Event()
            release = threading.Event()
            directories = []
            registry = MemoryCourseRegistry()
            original_stage = courses._stage_files

            def blocked_stage(files, directory):
                directories.append(Path(directory))
                loop.call_soon_threadsafe(started.set)
                if not release.wait(5):
                    raise AssertionError("Staging was not released")
                self.assertTrue(Path(directory).is_dir())
                return original_stage(files, directory)

            def blocked_extract(path):
                directories.append(path.parent.parent)
                loop.call_soon_threadsafe(started.set)
                if not release.wait(5):
                    raise AssertionError("Extraction was not released")
                self.assertTrue(path.is_file())
                return extract_material(path)

            target, replacement = (("backend.app.api.courses._stage_files", blocked_stage)
                                   if phase == "staging" else
                                   ("backend.app.ingestion.pipeline.extract_material", blocked_extract))
            with self.subTest(phase=phase), patch.dict(os.environ, {"MODEL_PROVIDER": "fake", "DYNAMODB_TABLE_NAME": ""}), \
                    patch(target, side_effect=replacement):
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=upload_app(registry)),
                                              base_url="http://test") as client:
                    task = asyncio.create_task(client.post("/api/v1/courses", files=[upload()]))
                    try:
                        await asyncio.wait_for(started.wait(), 3)
                        task.cancel()
                        await asyncio.sleep(0)
                        self.assertFalse(task.done())
                        self.assertTrue(all(path.exists() for path in directories))
                    finally:
                        release.set()
                        with self.assertRaises(asyncio.CancelledError):
                            await task
                self.assertTrue(all(not path.exists() for path in directories))
                self.assertEqual(registry._courses, {})

    async def test_extraction_is_off_loop_and_processing_concurrency_is_bounded(self):
        loop_thread = threading.get_ident()
        started = asyncio.Event()
        release = threading.Event()
        active = 0
        peak = 0
        lock = threading.Lock()
        loop = asyncio.get_running_loop()

        def slow_extract(path):
            nonlocal active, peak
            self.assertNotEqual(threading.get_ident(), loop_thread)
            with lock:
                active += 1
                peak = max(peak, active)
                if active == 2:
                    loop.call_soon_threadsafe(started.set)
            try:
                if not release.wait(5):
                    raise AssertionError("Event loop failed to release extraction workers")
                return extract_material(path)
            finally:
                with lock:
                    active -= 1

        with patch.dict(os.environ, {"MODEL_PROVIDER": "fake", "DYNAMODB_TABLE_NAME": ""}), \
                patch("backend.app.ingestion.pipeline.extract_material", side_effect=slow_extract):
            app = upload_app(MemoryCourseRegistry())
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                tasks = [asyncio.create_task(client.post("/api/v1/courses", files=[upload()])) for _ in range(3)]
                try:
                    await asyncio.wait_for(started.wait(), 3)
                    demo = await asyncio.wait_for(client.post("/api/v1/sessions", json={}), 1)
                    self.assertEqual(demo.status_code, 201)
                    self.assertFalse(any(task.done() for task in tasks))
                finally:
                    release.set()
                    responses = await asyncio.gather(*tasks)
                self.assertEqual([r.status_code for r in responses], [201] * 3)
                self.assertEqual(peak, 2)
