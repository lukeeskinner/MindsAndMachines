"""Multipart ingestion router; mount with the same registry as session routes."""
import asyncio
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
            return HTTPException(504, "Course generation timed out.")
        return HTTPException(502, "Course generation provider failed.")
    if str(exc) == ("PDF extraction requires existing Poppler pdfinfo and pdftotext "
                    "on PATH; nothing was installed."):
        return HTTPException(503, "PDF extraction is unavailable; Poppler is required on the server.")
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
