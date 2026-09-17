# Course upload API handoff

Scope: `codex/upload-ingestion-api`, integrated on fetched main
`4f1d7d06b93c983ff7e9ae0baa9d218d6f67e831` (dynamic runtime merge #12).
This work owns the dedicated
`api/courses.py` router, HTTP integration tests, multipart dependency/lock entry,
and a small ingestion scheduling change, plus a two-line composition-root addition.
The existing session/turn route file is unchanged; no learning activation is included.
Main's single-call concept/question/teaching generation and teaching validation
remain intact. The pipeline additions only share the file-count limit and move
extraction off the request loop with cancellation-safe temporary-file ownership.

## Request and response

`POST /api/v1/courses` accepts `multipart/form-data` with 1–8 repeated `files`
parts and an optional `title` text field (default `Uploaded course`, 1–200
characters). Provider selection follows the existing server `MODEL_PROVIDER`
configuration: fake/local is deterministic, Bedrock is explicit. Clients cannot
select a provider. No live AWS calls are part of verification.

Success is HTTP 201 with the existing `PublicCourse` shape:

```json
{
  "course_id": "course_...",
  "title": "Graph search",
  "concepts": [{"concept_id": "concept_...", "display_name": "Admissibility"}],
  "source_filenames": ["lecture.pdf", "slides.pptx"],
  "question_count": 4
}
```

The full immutable artifact is registered in the supplied `MemoryCourseRegistry`.
Equal artifacts can be registered repeatedly; different content with the same ID
returns 409 without replacing the stored artifact. Nothing mutates the demo
catalog. Metadata comes exclusively from `registry.catalog(id).public_metadata()`;
no answers, rubrics, explanations, summaries, quotes, prompts, teaching internals or processing
metadata are serialized. This existing public contract has no generation-mode or
review-status field: success must not be presented as reviewed or study-ready.
Course sessions remain previews; course turns remain disabled in this branch.

## Validation and cleanup

Only `.pdf`/`.pptx` extensions, case-insensitive, are accepted. MIME labels are not
trusted as proof of format; the existing extractors validate content. Each file is
limited to the ingestion constant of 20 MiB during multipart parsing, before an
oversized file can finish spooling. The parser limits file count to the pipeline's
shared eight-file constant and text fields to one small title. The full multipart
body is capped at eight file limits plus 64 KiB of envelope overhead, including
chunked requests with no Content-Length. Missing/truncated multipart bodies,
unknown fields and invalid titles are rejected.

Plain original filenames are preserved, including case and spaces, in separate
server-generated temporary subdirectories. Remaining path separators/control
characters and names over 255 UTF-8 bytes are rejected. The multipart library
normalizes legacy Windows absolute paths to their original basenames. Duplicate
basenames never overwrite each other; duplicate material rejection remains in
ingestion. Raw upload spools and staged files are closed/removed on success and
failure. No raw files are persisted permanently. Private extracted text remains
inside the existing process-local course artifact, as before.

Extraction's page/slide, expanded archive, text, evidence, generated-content and
provider-context limits are unchanged. Partial extraction retains the pipeline's
existing semantics and private warnings; ingestion success is not a claim that
every page was readable. Poppler must already be installed for PDF extraction.

## Scheduling and errors

Each router allows two active upload operations across parsing, staging,
processing and registration. File copying runs in the thread pool.
`process_course` moves synchronous extraction to `asyncio.to_thread`; its public
signature and results are unchanged. Generation still uses the original async
provider call on the request loop, preserving its timeout rather than nesting it
in a worker-owned event loop. Cancellation waits for active staging/extraction
threads before deleting their input files. The provider's existing late SDK
result behavior is unchanged. There are no queues, detached jobs or new services.

Errors use fixed `{"detail": "..."}` messages and never echo exception text,
source materials, prompts, provider payloads or credentials:

| Status | Meaning |
| --- | --- |
| 413 | File/request byte limit exceeded |
| 415 | Unsupported media type or filename extension |
| 422 | Invalid multipart fields/count/title/filename, extraction or ingestion validation failure, malformed generated course |
| 503 | Required Poppler executables unavailable |
| 502 | Provider failure |
| 504 | Provider deadline exceeded |
| 409 | Existing registry artifact conflicts with generated course |
| 500 | Unexpected upload/processing failure |

The ingestion seam currently exposes one `IngestionError` type. Provider errors
are classified through its typed cause; Poppler unavailability matches only its
known fixed message. Other validation errors share a generic 422. These messages
avoid widening shared error contracts in this branch.

## App composition

`backend/app/main.py` imports:

```python
from backend.app.api.courses import course_router_for
```

Inside `create_app`, after constructing `course_registry` and before the frontend
static mount, it mounts:

```python
app.include_router(course_router_for(course_registry))
```

This is the **same** registry instance already passed to the session router. No
shared contracts, runtime classes or existing router signatures need changes.
The default app now exposes the endpoint. HTTP tests use `create_app` directly,
exercising upload → registration → preview session end to end, and check that
separate apps keep separate registries. Uploaded artifacts include all three
teaching kinds per concept and can build a validated runtime catalog privately.
HTTP course turns still retain the foundation's 409 guard.

An example request is:

```sh
curl -F 'title=Graph search' -F 'files=@lecture.pdf' -F 'files=@slides.pptx' \
  http://127.0.0.1:8000/api/v1/courses
```

No auth, discovery, durable course storage, frontend, DynamoDB, deployment or
uploaded-course tutoring changes are included. The integrator must retain the
existing distinction between course preview and enabled study.

## Verification commands

```sh
backend/.venv/bin/python -m unittest discover -s tests/integration -p test_course_uploads.py -v
backend/.venv/bin/python -m unittest discover -s backend/tests/ingestion -v
backend/.venv/bin/python -m unittest discover -s backend/tests/storage -v
backend/.venv/bin/python -m unittest discover -s tests/integration -p test_course_sessions.py -v
make check
make smoke
git diff --check
```

Upload tests are included in `make check` through existing integration discovery.
Ingestion regression remains the separate command above. Tests use real synthetic
PDF/PPTX fixtures and mocked provider responses/errors, including size limits,
temporary cleanup, registration conflicts, privacy, cancellation, two-upload
concurrency and a responsive demo request while extraction is blocked.

Verified after integration on `4f1d7d0`:

- Upload API: 19 passed through the actual app, including private teaching
  artifacts, runtime catalog construction and a mocked single-call generation.
- Ingestion: 40 passed, including actual local Poppler extraction and teaching
  generation/validation regression. No live AWS calls.
- `make check`: 283 backend tests, frontend typecheck/build and all 27 frontend
  tests passed. Backend coverage includes all 47 integration tests, 133 teaching
  tests (17 runtime catalog, 76 Tutor, 15 course personalization and other
  teaching checks), 15 storage tests and 7 course/session integration tests.
  Existing Vite sourcemap/`use client` and jsdom `scrollTo` warnings remain.
- `make smoke`: passed the real HTTP demo, reset and preference isolation with
  localhost binding enabled.
- `git diff --check` and new-file whitespace checks passed.

Existing installed dependencies were copied into this isolated worktree; the new
multipart dependency was installed and locked here. No fresh full dependency
setup, live AWS test or browser walkthrough is claimed. GitHub CLI is unavailable;
PR creation requires the manual comparison link. The approved upload work was
stashed (including untracked files), the branch fast-forwarded to the dynamic
runtime merge, and the stash reapplied without conflicts. A reviewed diff against
that main commit confirms the pipeline's teaching behavior is unchanged. The
backup stash remains available. Router composition is complete; no shared
contracts, session/turn runtime activation or deployment changes were made.
