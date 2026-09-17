"""Multipart ingestion router; mount with the same registry as session routes."""
import asyncio
import logging
from pathlib import Path
import tempfile

from fastapi import APIRouter, HTTPException, Request
from python_multipart.exceptions import MultipartParseError
from python_multipart.multipart import parse_options_header
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from backend.app.agents.provider import ProviderError
from backend.app.ingestion import IngestionError, process_course
from backend.app.ingestion.extraction import MAX_FILE_BYTES
from backend.app.ingestion.pipeline import MAX_FILES
from backend.app.storage.courses import MemoryCourseRegistry
from contracts.models import PublicCourse


logger = logging.getLogger("uvicorn.error.ingestion")
# Only fixed codes reach logs. Never log exception text, source content or a
# provider response; validation exceptions may retain private materials.
_FAILURE_REASONS = {
    "The source supports a practice pool but fewer than three safe questions survived.": "insufficient_safe_pool",
    "Generated JSON has missing or unexpected fields.": "generated_schema",
    "Generated text is empty, invalid, or too long.": "generated_text_bounds",
    "Generated list has an invalid type or size.": "generated_list_bounds",
    "Generated JSON contains duplicate object keys.": "duplicate_json_key",
    "Generated JSON contains a non-JSON numeric constant.": "invalid_json_number",
    "Generated JSON exceeds the output limit.": "generated_output_limit",
    "Provider returned malformed JSON.": "malformed_generated_json",
    "Unknown or duplicate generated passage ID.": "invalid_passage_id",
    "Generated answer ID does not belong to its passage.": "invalid_answer_reference",
    "No usable source passages for question generation.": "no_usable_passages",
    "Every runtime concept needs at least one usable grounded question.": "insufficient_safe_questions",
    "Generated question prompt discloses its answer.": "question_answer_leakage",
    "Generated question asks for a false or mistaken statement.": "negative_question",
    "Generated plan concept list has an invalid type or size.": "invalid_plan_concept_count",
    "Generated plan question list has an invalid type or size.": "invalid_plan_question_count",
    "Generated plan distractor list has an invalid type or size.": "invalid_plan_distractor_count",
    "Unknown source reference or unsupported evidence quote.": "unsupported_evidence_quote",
    "Duplicate source reference.": "duplicate_source_reference",
    "Duplicate concept.": "duplicate_concept",
    "Concept name and summary must be supported by the same source quote.": "concept_source_mismatch",
    "Duplicate concept ID.": "duplicate_concept_id",
    "Question choices or answer key are invalid.": "invalid_question_choices",
    "Duplicate question prompt.": "duplicate_question_prompt",
    "Duplicate question content.": "duplicate_question_content",
    "Question does not identify its concept.": "question_concept_mismatch",
    "Question evidence must intersect its concept's sources.": "question_source_mismatch",
    "Question answer and explanation lack shared source evidence.": "answer_source_mismatch",
    "Multiple choices appear in source evidence; extractive question is ambiguous.": "ambiguous_question",
    "Duplicate question ID.": "duplicate_question_id",
    "Expected exactly one teaching item per intervention kind.": "missing_teaching_kind",
    "Invalid teaching identity, concept or kind.": "invalid_teaching_identity",
    "Invalid teaching paragraphs.": "invalid_teaching_paragraphs",
    "Probe or hint exceeds the teaching budget.": "teaching_length_limit",
    "Teaching lacks valid concept source references.": "teaching_source_mismatch",
    "Teaching contains a private rubric or correct-choice text.": "teaching_answer_leakage",
    "Teaching contains control instructions or answer disclosure.": "teaching_control_or_answer",
    "Teaching exposes internal identifiers.": "teaching_internal_identifiers",
    "Teaching prose is not supported by cited text or a process template.": "unsupported_teaching_prose",
    "Bedrock context exceeds 24,000 characters; split the material before processing.": "source_context_limit",
    "No extractable text; scanned pages/images need OCR outside this MVP.": "no_extractable_text",
    "Unexpected provider response; course generation rejected.": "unexpected_provider",
}


class UploadTooLarge(MultiPartException):
    pass


class CourseMultipartParser(MultiPartParser):
    """Bound file bytes while parsing, before a whole oversized file is spooled.

    Starlette's max_part_size only bounds text fields. Its spool cleanup list is
    also closed on disconnect/malformed input, not just MultiPartException.
    """

    finished = False

    def on_part_begin(self):
        super().on_part_begin()
        self.part_bytes = 0

    def on_part_data(self, data, start, end):
        self.part_bytes += end - start
        if self.part_bytes > MAX_FILE_BYTES:
            raise UploadTooLarge("File size limit exceeded.")
        super().on_part_data(data, start, end)

    def on_end(self):
        self.finished = True

    async def parse(self):
        try:
            form = await super().parse()
            if not self.finished:
                raise MultiPartException("Incomplete multipart body.")
            return form
        except BaseException:
            for stream in self._files_to_close_on_error:
                stream.close()
            raise


async def _bounded_stream(request):
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_FILES * MAX_FILE_BYTES + 64 * 1024:
            raise UploadTooLarge("Request size limit exceeded.")
        # Bound synchronous parser work per event-loop iteration as well.
        for offset in range(0, len(chunk), 64 * 1024):
            yield chunk[offset:offset + 64 * 1024]
            await asyncio.sleep(0)


def _stage_files(files, directory):
    paths = []
    for index, upload in enumerate(files):
        # Separate server-selected directories preserve duplicate basenames
        # without overwriting files or changing ingestion's stable IDs.
        folder = Path(directory) / str(index)
        folder.mkdir()
        path = folder / upload.filename
        total = 0
        with path.open("xb") as target:
            while chunk := upload.file.read(64 * 1024):
                total += len(chunk)
                if total > MAX_FILE_BYTES:
                    raise HTTPException(413, "Each source file must be at most 20 MB.")
                target.write(chunk)
        paths.append(path)
    return paths


async def _stage_uploads(files, directory):
    staging = asyncio.create_task(run_in_threadpool(_stage_files, files, directory))
    try:
        return await asyncio.shield(staging)
    except asyncio.CancelledError:
        await asyncio.gather(staging, return_exceptions=True)
        raise


def _ingestion_error(exc):
    # Never serialize exception text, attached materials or chained exceptions.
    if isinstance(exc.__cause__, ProviderError):
        if isinstance(exc.__cause__.__cause__, TimeoutError):
            logger.warning("course_ingestion_failed reason=provider_timeout")
            return HTTPException(504, "Course generation timed out.")
        logger.warning("course_ingestion_failed reason=provider_failure")
        return HTTPException(502, "Course generation provider failed.")
    if str(exc) == ("PDF extraction requires existing Poppler pdfinfo and pdftotext "
                    "on PATH; nothing was installed."):
        logger.warning("course_ingestion_failed reason=pdf_extractor_unavailable")
        return HTTPException(503, "PDF extraction is unavailable; Poppler is required on the server.")
    logger.warning("course_ingestion_failed reason=%s", _FAILURE_REASONS.get(str(exc), "unclassified_validation"))
    return HTTPException(422, "Course ingestion failed validation. Check the source files and try again.")


def course_router_for(registry: MemoryCourseRegistry) -> APIRouter:
    router = APIRouter(prefix="/api/v1")
    processing_slots = asyncio.Semaphore(2)

    @router.post("/courses", response_model=PublicCourse, status_code=201)
    async def upload_course(request: Request) -> PublicCourse:
        media_type, _ = parse_options_header(request.headers.get("content-type", ""))
        if media_type != b"multipart/form-data":
            raise HTTPException(415, "Use multipart/form-data with PDF/PPTX files.")
        # Bound parsing/staging/extraction/provider work per app router. The
        # provider retains its own deadline and late-SDK-result handling.
        async with processing_slots:
            parser = CourseMultipartParser(request.headers, _bounded_stream(request),
                                           max_files=MAX_FILES, max_fields=1, max_part_size=1024)
            try:
                form = await parser.parse()
            except UploadTooLarge:
                raise HTTPException(413, "Upload exceeds the source file or request size limit.") from None
            except (MultiPartException, MultipartParseError):
                raise HTTPException(422, "Invalid multipart upload; supply 1–8 files and an optional title.") from None
            except Exception:
                raise HTTPException(500, "Upload processing failed.") from None
            try:
                files = form.getlist("files")
                title = form.get("title", "Uploaded course")
                if (set(form) - {"files", "title"} or not 1 <= len(files) <= MAX_FILES
                        or not all(isinstance(file, UploadFile) for file in files)
                        or not isinstance(title, str) or not title.strip() or len(title) > 200):
                    raise HTTPException(422, "Supply 1–8 files and a nonempty title of at most 200 characters.")
                for upload in files:
                    name = upload.filename
                    if (not name or len(name.encode("utf-8")) > 255
                            or any(char in name for char in "/\\")
                            or any(ord(char) < 32 or ord(char) == 127 for char in name)):
                        raise HTTPException(422, "Source filenames must be plain filenames without paths.")
                    if Path(name).suffix.lower() not in {".pdf", ".pptx"}:
                        raise HTTPException(415, "Only PDF and PPTX files are supported.")
                with tempfile.TemporaryDirectory(prefix="course-upload-") as directory:
                    paths = await _stage_uploads(files, directory)
                    try:
                        course = await process_course(paths, title=title)
                    except IngestionError as exc:
                        raise _ingestion_error(exc) from None
                try:
                    course_id = registry.register(course)
                except ValueError:
                    raise HTTPException(409, "Course registration conflicts with an existing artifact.") from None
                return registry.catalog(course_id).public_metadata()
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(500, "Course processing failed.") from None
            finally:
                await form.close()

    return router
