# Standalone course ingestion

This module processes PDF/PPTX into an immutable **server-only** course artifact.
The processing pipeline remains standalone. The
[course/session foundation](../../../docs/COURSE_SESSION_FOUNDATION.md) now offers
explicit private registration, public metadata and preview sessions for completed
artifacts. A separate [upload router](../api/COURSE_UPLOADS.md) now implements the
HTTP boundary and is mounted with the app-owned course registry. Uploaded-course learning is
not activated; processing itself does not call storage, the API or learning runtime.

From the repository root, using Python 3.12 or 3.13:

```sh
python3 -m backend.app.ingestion --title 'Graph search' --mode local \
  backend/tests/ingestion/fixtures/course.pdf \
  backend/tests/ingestion/fixtures/course.pptx > /tmp/processed-course.json
python3 -m unittest discover -s backend/tests/ingestion -v
```

The output file includes answers and source excerpts: do not serve it directly to
the browser or commit uploaded material/student data. CLI errors go to stderr with
a nonzero exit code and no partial JSON on stdout. For extraction diagnostics,
use the functions below; `IngestionError.materials` preserves extraction records
when generation or input-quality checks fail after extraction.

```python
from backend.app.ingestion import extract_material, process_course

source = extract_material('lecture5.pdf')
# In an async function; use asyncio.run(...) from a synchronous script.
course = await process_course(
    ['lecture5.pdf', 'lecture6.pptx'], title='Intro AI', mode='local'
)
server_data = course.to_dict()
public_question = course.questions[0].public()
```

## Extraction and dependencies

PDF uses `pdfinfo` to count pages and `pdftotext` once per page, with UTF-8 output
and a 15-second timeout per subprocess. Both executables must be on PATH. Poppler
25.09.1 was already installed in the development environment; no package was
installed and no pyproject/lockfile was changed. **Poppler is a system prerequisite
not provisioned by `make setup`**. Missing executables raise an actionable error;
the module never installs anything or substitutes fake text. A deployment or
developer machine without Poppler needs a separately approved dependency/setup
decision. Extraction-only PPTX and local generation need only the standard library.

PPTX reads slide order through `ppt/presentation.xml` and its relationships,
then gathers DrawingML paragraph text from shapes/tables. Slide filename order
does not establish slide numbers. It does not extract the ZIP to disk, resolve
external relationships, execute embedded objects, or expand XML entities.
Speaker notes, master/layout text, diagrams without text, images, and OCR are out
of scope. PDF columns, formulas, and complex reading order may extract imperfectly.

Every page/slide has its original extraction text, whitespace-normalized text,
one-based location, stable chunk ID, and `extracted`, `empty`, or `unreadable`
status. Blank and image-only pages are `empty` (not an assertion that the visual
page is blank). A broken slide or PDF page keeps its original number; a document
whose page/slide structure cannot be read has no fabricated chunks. Poppler page
warnings are treated conservatively as unreadable. Partial material remains
available with warnings; no usable text causes an error, never invented content.

Limits: 1–8 files, 20 MB each, 1–100 pages/slides per file, 200,000 extracted
characters per file, PPTX at most 2,000 archive members/40 MB expanded. Bedrock
receives at most 24,000 normalized source characters; larger input is rejected
with a request to split it, rather than silently dropping source content.
Extraction is synchronous local work; `process_course` now runs that extraction
in `asyncio.to_thread`, while leaving the bounded provider coroutine on the caller's
event loop. The upload router bounds active processing to two requests. Cancellation
waits for extraction to finish before the caller can remove temporary inputs.

## Internal schema (version 1)

All records are frozen dataclasses and collections are tuples. `to_dict()` gives
a detached structure that serializes to JSON arrays/objects.

| Record | Fields |
| --- | --- |
| ProcessedCourse | `course_id`, `title`, `materials`, `concepts`, `questions`, `metadata`, `teaching` (default empty for legacy constructors) |
| SourceMaterial | `material_id`, original basename `filename`, `sha256`, `format`, `chunks`, `status`, `issues` |
| SourceChunk | `chunk_id`, `location_kind` (`page`/`slide`), `number`, original `text`, `normalized_text`, `status` |
| SourceReference | `chunk_id`, exact normalized-text `quote` |
| Concept | `concept_id`, `name`, extractive `summary`, `source_refs` |
| Question | `question_id`, `concept_id`, `prompt`, `choices[{id,text}]`, server-only `answer_key`, `explanation`, `source_refs` |
| TeachingArtifact | `teaching_id`, `concept_id`, `kind`, `paragraphs`, `source_refs`, `requires_review=true` |
| ProcessingMetadata | `schema_version`, `mode` (`local`/`bedrock`), `provider_calls`, `warnings`, `requires_review=true` |

Code alone assigns IDs, filenames, page/slide numbers, and extracted text. Material
IDs hash the original basename plus source bytes. Chunk IDs hash material ID and
location. Course IDs hash schema version, title, and sorted material IDs. Concept
IDs hash course ID, normalized name and sorted source IDs; question IDs hash the
concept, prompt, choices, answer, and evidence. Identical inputs/results produce
identical IDs, including across directories; source-byte, filename, title, or
generated content changes may change IDs. Semantically equivalent but different
files/model outputs are not promised identical IDs. Duplicate material is rejected.

## Local and Bedrock generation

`fake` and `local` are identical deterministic demo modes. They bypass the provider
entirely and build two source-recall MCQs for each of up to four distinct readable
source sections with at least eight words. A source heading supplies the concept
name where possible. These are honest source-derived fixtures, not a full semantic
topic detector, calibrated assessment, or unrelated fixed Intro AI demo. Both
modes run the same validation and record `mode=local`, `provider_calls=0`.

`process_course` follows `MODEL_PROVIDER` when `mode` is omitted, defaulting to
fake if unset. The CLI deliberately defaults to local even if that environment
variable is set. Bedrock requires both `mode=bedrock` (or the function's env default)
and `MODEL_PROVIDER=bedrock`; it reuses `backend.app.agents.provider.complete`
without changing provider configuration or introducing an adapter. Use the
existing backend environment and already configured AWS region/model/credentials.

```sh
MODEL_PROVIDER=bedrock python3 -m backend.app.ingestion \
  --mode bedrock --title 'Graph search' lecture5.pdf
```

The same response now also includes exactly three teaching items per concept:
`diagnostic_probe`, `worked_example` and `socratic_hint`. Each has `kind`,
`paragraphs` and `source_refs`; trusted code assigns its stable ID and review flag.
Subject prose must be cited excerpts or fixed process templates, and all kinds
reject direct copying of any course answer/rubric. Local mode uses conservative
process templates without a provider. See [runtime catalog](../teaching/RUNTIME_CATALOG.md)
for the disclosure checks, their limitations, deterministic rendering and optional
Bedrock Tutor personalization. Course processing still has only one provider call.

There is exactly one provider call with a 6,000-token output budget. The existing
provider deadline/retry policy applies. Generation returns 1–4 concepts and 2–4
questions each, at most 16 total. No retries, repair calls, provider switching, or
automatic local fallback occur. Malformed/unsupported output and provider failures
raise `IngestionError`; callers may explicitly request a separate local run.
Model output can vary between runs; this branch does not claim Bedrock determinism.

The model receives chunk IDs and normalized text, without filenames or location
metadata. Strict JSON requires exact keys/types, bounded nonempty lists/text,
and no duplicate object keys or NaN/Infinity. Extra ID/provenance fields are
rejected. Concepts require unique names and source-verbatim names/summaries.
Questions require distinct prompts/choices, an integer answer index, their
concept name in the prompt, and known nonempty source references. Every quote
must occur in the cited chunk. Correct answer text and explanation must occur
in a shared evidence quote from one of the concept's source chunks. Distractors
appearing verbatim in evidence are rejected as ambiguous for this extractive MVP.

These checks detect some unsupported answers and references; they cannot prove
that a prompt entails its answer, that distractors are false, that course coverage
is adequate, or that the source itself is correct. Human review remains required
before integration. Uploaded instructions remain data, with no tools or agent
execution available to the generation step.

## Exact later integration boundary

1. The dedicated upload router supplies controlled local PDF/PPTX paths and a title to
   `await process_course(paths, title=title, mode=mode) -> ProcessedCourse`; handle
   `IngestionError` without exposing raw provider exceptions. Upload transport,
   validation and temporary cleanup live in that API module; authentication and
   durable persistence are not implemented here. See its handoff for composition.
2. Register the artifact privately with `MemoryCourseRegistry.register(course)`.
   This keeps the full artifact in process memory; durable persistence is deferred.
   Resolve each reference via `materials[].chunks[].chunk_id` to its filename and
   page/slide number. IDs/location metadata must continue to come from trusted code.
3. `storage.courses.adapt_question` now constructs the server `Question` from
   the local question's `question_id`, `concept_id`, `prompt`, `choices`, and
   `answer_key`, with `rubric=explanation`. It retains source references separately
   in `AdaptedQuestion.source_refs`. `question.public()` exposes only the
   existing PublicQuestion-shaped fields and omits source answers/explanations.
4. Call `teaching.runtime_catalog.build_runtime_catalog(course)` to build isolated
   runtime questions, candidates and stored teaching content. It appends `unsure`
   to runtime question copies and supplies explicit freshness/exhaustion helpers.
   Tutor renders stored artifacts without a call in fake/local mode. In Bedrock
   mode it may personalize them with one existing-adapter call per teaching turn,
   falling back to the stored artifact on failure. Legacy artifacts without
   teaching require explicit reprocessing. Content remains marked for human review;
   no prerequisites, calibrated difficulty or learned treatment effects are added.
   Initialize learner state from accepted concept IDs only; processing/teaching
   must never raise mastery by itself. HTTP runtime activation is still separate.
5. Integrator may add ingestion discovery to `make check`; this branch runs
   `python3 -m unittest discover -s backend/tests/ingestion -v` separately so the
   shared Makefile stays unchanged. Run the existing `make check` and `make smoke`
   alongside that command before integration.

Fixtures are synthetic, authored specifically for tests. The PDF has compressed
text on pages 1 and 3 plus a blank page 2. The PPTX has readable slides 1 and 3
plus an empty slide 2. Fixture authoring used already bundled ReportLab/python-pptx;
neither is an ingestion or test runtime requirement. No live AWS calls run in tests.
