# Course/session integration foundation

Historical foundation handoff: its preview-only 409 guard is superseded by the
[uploaded-course runtime integration](UPLOADED_COURSE_INTEGRATION.md).

This slice establishes private artifact ownership and preview session creation.
It does not activate uploaded-course learning. The default demo, FakeAssessor,
BayesianLearner, AdaptivePolicy, Coordinator and Tutor remain unchanged.

## Private ownership and lookup

`backend/app/storage/courses.py` owns `MemoryCourseRegistry`. Each app gets an
empty registry unless one is explicitly injected via
`create_app(course_registry=registry)`. Future server-side ingestion can call
`registry.register(processed_course)` and retain the returned course ID. There
is no registration/upload HTTP endpoint and no global mutable course catalog.

The existing immutable `ProcessedCourse.course_id` is reused. Ingestion derives
it from schema version, title and sorted material IDs. It remains stable for the
stored artifact's lifetime. Re-registering an equal artifact succeeds; attempting
to replace it with different content under the same ID raises `ValueError`.
Generation can produce different content for identical sources/IDs: this branch
rejects that conflict instead of changing what existing sessions reference.
Artifact revision/replacement is a later explicit design decision.

The registry stores the entire immutable artifact, including private answer keys,
explanations, processing metadata and source material. `get(course_id)` returns
that artifact for trusted backend callers; `catalog(course_id)` returns a
course-scoped `CourseCatalog`. Unknown IDs raise `KeyError`; there is no demo
fallback for an explicitly supplied unknown course. Empty artifacts are rejected.
The registry expects validated ingestion output, not arbitrary client JSON.

The follow-on lookup path is:

```python
session = store.load_session(session_id)
if session.course_id is not None:
    catalog = registry.catalog(session.course_id)
    artifact = catalog.course                  # private ProcessedCourse
    concepts = artifact.concepts               # private summaries/provenance
    adapted = catalog.question(session.question_id)
    question = adapted.question                # contracts.models.Question
    provenance = adapted.source_refs           # private source references
    metadata = catalog.public_metadata()       # contracts.models.PublicCourse
```

`CourseCatalog` provides `concept_ids`, `first_question_id`, `question(id)` and
`public_metadata()`. It deliberately has no Tutor content or policy candidates.
An unknown question raises `KeyError` within that course. Each conversion creates
a fresh runtime Question; modifying it cannot modify the stored immutable source.

## Session contract and reset

`POST /api/v1/sessions` accepts an optional `course_id`. Absent/empty request body
or null course ID starts the existing demo. A known course starts a preview with
the first source question, concept priors and no history/evidence. Unknown course
IDs return 404 before state creation; malformed request fields return 422.
`SessionResponse` adds `course_id: string|null`; the question shape stays unchanged.
The Python/TypeScript types are updated together; the existing turn fixture is
unchanged because TurnResponse is unchanged.

`Session.course_id` defaults to None. Multiple sessions can share one course but
own separate learner state/history. Reset remains session creation: explicitly
resend the same course ID to retain selection; omission/null selects the demo.
Old sessions are not modified. The current frontend still creates demo sessions.

Course sessions return HTTP 409 (`Course learning is not enabled yet.`) for every
turn, before catalog lookup, assessment, policy, teaching or state updates.
The initial question is only a preview, not a promise that study is available.
Later UI work must represent that distinction until activation is authorized.

MemoryStore retains the reference. DynamoStore adds only this optional scalar to
its existing session JSON and reads missing legacy values as None. No table schema
changes or processed-course persistence were introduced. Registries are lost on
restart; DynamoDB sessions may outlive their referenced artifacts. Later activation
must restore/validate course availability and fail safely, never fall back to a
different/demo course. This is artifact ownership, not per-user access control;
future upload/discovery must define authorization before exposing private data.

## Public projection, adapter and abstention

`PublicCourse` explicitly projects course ID, title, concept IDs/display names,
source basenames and question count. Private summaries, quotes, warnings, answer
keys and explanations are excluded. No public course lookup endpoint is added.
The existing ingestion pipeline supplies source basenames, never filesystem paths.

`adapt_question(ingestion_question)` returns `AdaptedQuestion(question, source_refs)`.
It maps question/concept IDs, prompt, choices and answer key directly, and maps
`explanation` to `rubric`. `question.public()` exposes only IDs, prompt and choices.
References remain separate; their chunk IDs resolve through the original artifact
to material filename, page/slide number and exact evidence quote. Quotes and
rubrics never become public response fields.

Choices are preserved exactly. Generated questions currently omit `unsure`, while
the demo route accepts only listed choice IDs. Before activation, either the
generated-course adapter must add an explicit unsure choice with agreed semantics,
or the route contract must support abstention. This branch does neither.

## Follow-on work and shared-file coordination

The next integration can register ingestion output, resolve course-specific
questions/concepts and use public metadata without altering the demo catalog.
It still needs reviewed content, course-specific teaching catalogs/candidates,
abstention handling, deliberate runtime/assessor wiring and UI activation. Do not
remove the 409 guard until those pieces are integrated and verified together.

Shared seams needing coordinated review are `contracts/models.py`,
`contracts/api.ts`, `main.create_app`, `api.routes.router_for`, and both stores'
`new_session` signatures. Course identity conflict behavior and preview/reset
semantics must remain consistent across later upload/runtime/UI workstreams.
This branch adds no upload, progression, deployment or live AWS calls.

Foundation tests are in `backend/tests/storage/test_courses.py`, the DynamoStore
serialization tests, and `tests/integration/test_course_sessions.py`; all are
included by `make check`. Ingestion remains a separate regression command:
`backend/.venv/bin/python -m unittest discover -s backend/tests/ingestion -v`.

## Verification for this handoff

Base: `codex/course-session-foundation` at
`34a03f881b7bc0c856558247169cdfbf1e314a75`, equal to fetched `origin/main`;
initial worktree clean. Work remains uncommitted.

- Focused registry, session and DynamoStore suite: 22 tests passed.
- `make check`: 232 backend tests passed, including RealAssessor, Coordinator,
  Tutor, BayesianLearner, AdaptivePolicy, storage and integration coverage;
  frontend typecheck/build and 27 frontend tests passed. Vite emitted nonfatal
  sourcemap/`use client` warnings in existing frontend/dependency files.
- Separate ingestion regression: 30 tests passed, including real local PDF/PPTX
  extraction. No Poppler provisioning or live AWS calls.
- `make smoke`: passed the actual HTTP demo, all three interventions, posterior
  values, reset and preference isolation. The initial sandbox bind was denied;
  the permitted localhost rerun passed.
- `git diff --check` and whitespace checks for new files passed.

The path/contract review covers the assigned integration seam; learner, policy,
Coordinator, demo catalog and frontend source were not edited. HEAD matches the
fetched main, and no conflict markers were found. GitHub open-PR overlap and
mergeability could not be verified because `gh` is unavailable. No new manual
browser walkthrough, fresh dependency installation or human review is claimed;
checks used local copies of existing installed dependencies. No commit, push,
merge or deployment was performed. Technically ready to commit for coordinated
shared-contract review, with the activation and persistence limits above.
