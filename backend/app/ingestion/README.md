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

Bedrock returns a compact question plan referencing server-created source
passages by ID. Its schema enumerates valid passage IDs and requires
`first_question` / `second_question`, each with `prompt` and three
string fields `wrong_option_1` / `wrong_option_2` / `wrong_option_3`. These required
fields encode cardinality without relying only on array-size instructions.
The server assigns an exact source answer to each of the five possible question
slots and includes those assignments under `question_answers` in the request.
The model writes the question prompts and distractors for those answers;
it does not write citations, correct-choice text, answer indices or explanations.
A forced Bedrock tool response carries the plan as a structured object rather
than JSON embedded in prose. This is only an output envelope: no tool action is
executed and no tool-result or second inference call is sent. The server rejects
missing, multiple, mismatched or truncated tool responses. The server resolves
passage IDs only against this upload, inserts each slot's trusted answer and exact
source evidence, and runs the existing artifact validators. The model cannot
supply answer IDs or override the slot assignment. Unknown/duplicate passage IDs,
extra fields and ambiguous distractors are rejected.

Passages are contiguous normalized source windows of at most 800 characters.
Their labels use a short source heading where available, otherwise the first
seven words. Answers disclosed by the label are excluded. Candidate answers are source sentences with at least three words;
answers that would overlap stored guidance are excluded before generation.
When at least two numbered topic headings have multiple source sentences, the
server narrows generation to the first five such sections and requests two
questions per section through named output slots. Each slot's schema embeds its
exact source answer, so the model cannot shift a question onto another passage.
The slot also requires an `assigned_answer_echo`: a copy of the already assigned
correct option, giving the model a complete multiple-choice shape while it writes
three wrong alternatives. The server rejects any echo that differs from its
trusted answer and still inserts the correct choice itself. The echo is never
used as grading authority or exposed as a public field. This keeps a broad lecture from collapsing into repeated
questions about one generic subheading. Unstructured material retains model
selection of up to five passages. This remains extractive assessment;
labels and answer snippets are not a semantic curriculum analysis.

Each concept receives the existing three authored process-guidance artifacts:
`diagnostic_probe`, `worked_example` and `socratic_hint`. This is an explicit part
of the new generation contract, not a fallback after a rejected model response.
The prompt tells the model that code supplies this guidance. Source references,
IDs and review flags are assigned in code; all artifacts still pass answer-leakage
checks. Runtime Bedrock Tutor personalization remains unchanged. See
[runtime catalog](../teaching/RUNTIME_CATALOG.md) for its limits and draft notices.

Generation starts with one provider call with a 6,000-token output budget. It explicitly
uses `purpose="course_ingestion"`: `BEDROCK_INGESTION_TIMEOUT_SECONDS` defaults to
60 seconds and accepts values above zero up to 90. Interactive assessment/Tutor
calls retain `BEDROCK_TIMEOUT_SECONDS` (default 12, maximum 15) and their existing
stage budgets. An enclosing provider deadline still caps either purpose; SDK
retries remain disabled. Generation selects 1–5 passages and writes 2–5 questions
per passage, aiming for 5–10 questions total. Ten slots is the hard upper bound;
shorter valid banks are accepted. Invalid question slots permit exactly one
question-only repair. Question schemas, answer references, negative stems,
answer leakage, duplicate choices/content and source-overlapping distractors are
checked independently for each slot, using the existing validators.
Distractors are checked case-insensitively against both their assigned evidence
and the whole concept passage. A terminal prose punctuation change cannot hide
a source formula; mathematical operators remain significant. These checks reject
copied true alternatives, but do not prove that an arbitrary paraphrase is false.
The initial and repair instructions require exactly one objectively correct answer,
precise positive stems, distinct/non-equivalent choices and no repeated question
semantics within a concept. These are generation requirements, not claims of
semantic proof by the lexical validators.
`course_ingestion_ready` reports concept/question counts, provider-call count,
and repaired/discarded counts without logging source text or model output.

The repair request includes the original plan, trusted passages/slot answers, and
machine-readable `revision.failures` and `revision.repair_targets`. `repair_slots`
also pairs each target directly with its source topic, passage and assigned answer;
the model need not reconstruct those bindings from array indices. Each failure
identifies a JSON-pointer question path, a reason, and either the original duplicate
question path, overlapping distractor field/rule or matched negative-stem keyword.
Failures are collected across resolution and validation for the same repair attempt. The response
must be exactly `{"repairs": [{"question_id": "<target path>", "question": {...}}]}`,
covering every target once. Missing, repeated, foreign and extra routing fields
invalidate the repair envelope; the initial valid bank remains available. Question
contents are validated per slot, so one malformed repair does not discard other
successful repairs. The server overlays only targeted question wording; it preserves
all originally valid questions, passage assignments, source IDs and slot answers.
It resolves the original slots before filtering, so removing a question cannot
shift another question's answer assignment. An earlier repaired duplicate cannot
displace an originally valid later question.
Unknown/duplicate passage IDs and duplicate concepts fail without regeneration.
Both calls share a 90-second total deadline. An invalid question remaining after
repair is discarded, never exposed. A repair provider failure or deadline retains
the valid initial questions. Every surviving question and the complete surviving
bank pass all content/source/disclosure validators before registration. A concept
with no usable grounded question rejects the entire course; concepts are not silently
dropped. Initial malformed course structure, unknown source references, invalid
trusted answers and teaching/source integrity errors also remain fatal.

Runtime minimum: one concept, at least one usable question per concept, and all
three validated teaching kinds per concept. Runtime catalogs, freshness and policy
already support variable counts and transition/complete on exhaustion. Targeted
remediation replaces an existing fresh slot; it cannot replenish an exhausted
one-question concept. No runtime changes were made for partial acceptance.

Private metadata records actual `provider_calls`, `degraded`,
`discarded_question_count` and `repaired_question_count`; a failed repair is never
reported as successful. The HTTP response includes only the accepted question count,
not private diagnostics. No provider switching or invented fallback questions occur.
Logs include fixed failure codes, server-generated slot paths and allowlisted
keywords, never question/source text or raw model output.
Model output can vary between runs; this branch does not claim Bedrock determinism.

The model receives request-scoped passage IDs and slot-assigned answer text, without
filenames, internal chunk IDs or location metadata. A single complete outer Markdown fence (JSON or unlabeled) is accepted;
surrounding prose and multiple blocks are not. Its contents still undergo all
validation. Strict JSON requires exact keys/types, bounded nonempty lists/text,
and no duplicate object keys or NaN/Infinity. Extra ID/provenance fields are
rejected. Concepts require unique names and source-verbatim names/summaries.
Questions require distinct choices, an integer answer index, their
concept name in the prompt, and known nonempty source references. Every quote
must occur in the cited chunk. Correct answer text and explanation must occur
in a shared evidence quote from one of the concept's source chunks. Distractors
appearing verbatim (case-sensitive, after whitespace normalization) in any cited
evidence quote are rejected as ambiguous for this extractive MVP. For generated
plans that quote is the server-assigned correct answer itself. This rule detects
substring overlap, not semantic equivalence, vague stems or answer-reference mismatch.
Repeated multiple-choice stems are allowed when the choice sets differ. A repeated
stem with the same choices is rejected as `duplicate_question_content`, ignoring
case, whitespace and option order. This prevents correct-slot rotation from
disguising a copied question. Generation still requests distinct, specific prompts;
duplicate content triggers the bounded repair above. Remaining invalid slots are
omitted with private degraded-generation metadata; they are never made unique by
adding an arbitrary number to the prompt.

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
