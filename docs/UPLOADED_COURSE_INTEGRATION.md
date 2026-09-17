# Uploaded-course integration handoff

This integration activates the merged upload, course/session, runtime catalog,
RealAssessor and frontend workstreams. The older preview-only behavior documented
in COURSE_SESSION_FOUNDATION.md is superseded here. Publication to main was
authorized after the successful live upload/session verification. No deployment
was performed. Eight manual Bedrock diagnostic/verification calls used the calculus PDF under
explicit user approvals (the last approval allowed three calls, all three used);
automated checks use local/mocked providers only.

Files changed:

- `backend/app/main.py`: course-specific composition factory.
- `backend/app/api/routes.py`: session/runtime resolution and history filtering.
- `backend/app/agents/coordinator.py`: trusted progression and completion checks.
- `backend/app/agents/provider.py`: separate bounded ingestion timeout; interactive defaults unchanged.
- `backend/app/ingestion/pipeline.py`: ingestion timeout purpose, strict JSON parsing, source-plan resolution, and source-phrase local completion answers.
- `backend/app/ingestion/passages.py`: trusted passage/answer tables and the ID-based model plan contract.
- `backend/tests/ingestion/test_passages.py`: source-resolution and invalid-plan regressions.
- `backend/tests/ingestion/helpers.py`: mocked ID-based provider plans.
- `backend/tests/ingestion/test_ingestion.py` and `backend/tests/teaching/test_course_personalization.py`: migrated provider fixtures.
- `backend/app/api/courses.py`: allowlisted ingestion failure diagnostics without private content.
- `backend/tests/ingestion/test_teaching.py`: code-fence validation and common-word heading regressions.
- `backend/tests/agents/test_provider.py`: independent bounded ingestion timeout regressions.
- `backend/app/teaching/tutor.py`: authored concept-transition response.
- `frontend/src/lib/api.ts`: missing course/session recovery message.
- `frontend/src/components/course/CourseContext.tsx`: returns confirmed upload metadata to the start action.
- `frontend/src/components/onboarding/Onboarding.tsx`: uploads/activates selected materials before entering study.
- `frontend/tests/courses.test.tsx`: disappearing-course and onboarding activation regressions.
- `frontend/tests/onboarding.test.tsx`: explicit demo-only navigation without selected materials.
- `backend/tests/ingestion/fixtures/grad-algorithms.pptx`: synthetic algorithms fixture without demo-topic text.
- `tests/integration/test_course_sessions.py`: replaces obsolete 409 expectation.
- `tests/integration/test_course_uploads.py`: requires successful uploaded turns.
- `tests/integration/test_uploaded_course_runtime.py`: combined-path integration tests.
- `README.md`: current uploaded-course behavior and handoff link.
- `docs/COURSE_SESSION_FOUNDATION.md`: marks the preview-only handoff as historical.
- `docs/UPLOADED_COURSE_INTEGRATION.md`: this implementation/verification handoff.

## Runtime wiring

`POST /api/v1/courses` performs the existing synchronous multipart ingestion and
registers the private `ProcessedCourse` in the app's `MemoryCourseRegistry`. It
returns only `PublicCourse`. There is no polling endpoint.

`POST /api/v1/sessions` with `course_id` resolves that artifact and calls
`build_runtime_catalog`. Its first question follows concept/artifact order and
includes the runtime's `unsure` choice. Bayesian priors use only that course's
concept IDs. The course ID stays in the existing session record, in memory or
DynamoDB according to the existing configuration.

On `POST /api/v1/turns`, the API resolves the session's course again and builds a
fresh runtime view. The former unconditional 409 is replaced by this lookup and
validation. A missing artifact returns 404; an invalid/legacy artifact returns
422. Neither path grades, updates state, or silently substitutes demo content.
Stale/foreign question submissions and invalid answer IDs remain rejected.

The composition root binds the existing assessor, learner and policy to a new
`Tutor(runtime)`. The coordinator executes RealAssessor → BayesianLearner →
AdaptivePolicy → Tutor within the existing deadlines. Uploaded candidates,
questions and teaching all come from that runtime. No global catalog is mutated.
Two sessions share an immutable artifact, never learner state/history; two courses
never share their runtime lookups. A session without `course_id` keeps the demo
composition and behavior.

The runtime catalog filters the current question, every previously submitted
question (including unsure answers), and consumed candidates using session
history. AdaptivePolicy chooses among the remaining candidates for the current
concept; its arithmetic is unchanged. When that concept is exhausted, its
availability result supplies the first remaining question in concept/artifact
order. The coordinator and Tutor carry this explicit continuation with a null
intervention and an authored transition message. No synthetic assessment or
cross-concept evidence is introduced. Only actual course-question exhaustion
returns `next_question=null` and the course completion message. A premature null
policy decision or a changed candidate binding fails before state is saved.

## Assessment, teaching and public boundary

RealAssessor grades generated questions using trusted server-side answer keys.
Unknown question IDs need no misconception tag: `misconception_id=null` does not
block binary Bayesian evidence. `unsure` stays `unclear`, with `score=null` and no
evidence update. The current question still counts as consumed for progression.

Fake/local mode uses stored deterministic teaching with zero provider calls.
Bedrock mode retains the existing optional assessor enrichment and at most one
bounded Tutor personalization call per intervention. Upload generation is a
separate existing call. No new provider call or retry was added. Tutor sees the
selected artifact's display-safe grounding, while policy selection and next
question IDs remain server-controlled. Invalid, timed-out or failed Tutor output
uses stored fallback and preserves the same question. Concept transitions and
completion do not call the Tutor provider. Unreviewed teaching retains its draft
notice, including when personalization is accepted.

Public course/question/turn shapes are unchanged. Answer keys, private rubrics,
source-reference records and internal generation metadata are not serialized.
Existing public question prompts/choices and validated teaching paragraphs remain
intentional display content. The four assessor/learner/policy/teaching callable
interfaces are unchanged. Internal wiring additions needing review are the
route's course-coordinator factory, `Coordinator.course_progression`, and Tutor's
optional `continuation_question_id` constructor argument.

The merged frontend sends multipart `files` and optional `title`, waits for 201,
activates the returned course, and sends `course_id` when creating/resetting its
session. Course title and concept labels use returned metadata; questions and
next questions use the API response. The former preview-only error message now
handles a missing session/course. The title is the supplied course name (or
`Uploaded course`), not an inferred document heading; concept names and questions
are derived from uploaded material.

## Manual failure diagnosis and activation fix

The reported onboarding path was reproducible without a backend/runtime defect.
Selecting a file populated only `draft.files`. Uploading it separately populated
`CourseContext.upload.course`, but `selectedCourse` stayed null until a separate
**Activate course** click. Both onboarding **Open practice demo** buttons called
navigation directly regardless of selected files or ready uploads. Consequently,
`LearningWorkspace` called `createSession(null)`, which sent `{}`; the backend
correctly created a demo session. No valid uploaded session was overwritten.
This is failure class B: no uploaded course ID was supplied because activation
could be bypassed. It is not evidence of a lost backend course ID or a reset race.

Two new regressions reproduced this before the fix, on the setup form and setup
review: the observed first request was `/api/v1/sessions`, while the required first
request was `/api/v1/courses`. The previous explicit-activation tests passed and
did not exercise this bypass. One older onboarding test even expected a demo
session after local file selection; it now tests explicit demo entry without files.

Both onboarding start buttons now use one upload/activation path. With files
selected, **Upload and start course** waits for a validated HTTP 201 PublicCourse,
selects it, then enters study. If an upload is already ready, **Start uploaded
course** selects it directly. Processing disables the start buttons; failure stays
on setup without a demo session. The separate **Upload course** / **Activate
course** path still works. The existing keyed workspace clears the old demo
state on selection and reset already sends the active course ID.

The production upload adapter and RootApp tests verify both onboarding entry
points, the request ID, uploaded Study Desk labels/questions, reset, a previously
running demo, and failed-upload retry. A real TestClient upload of the synthetic
Grad Algorithms PPTX verifies a non-demo ID, the same ID in stored session state,
the runtime catalog's initial question, and exactly the source-derived concepts
Dynamic programming / Optimal substructure. The runtime was not changed for this
fix. Successful live Bedrock generation of the user's actual slides remains a
manual acceptance check.

## Calculus PDF ingestion diagnosis and final fix

The reported PDF extracts successfully: four pages, 6,474 normalized characters,
no extraction issues. Live diagnoses found three distinct provider-output failures:
malformed free-text JSON, source quotes omitting generated concept/answer fields,
and invalid question/option counts. In the source-evidence diagnostic, all four
concept names and summaries existed in their cited pages, but none shared a
complete evidence quote. The upload failed before registration; no course ID was
lost in the session path. Prompt clarification alone did not resolve generation.

The user explicitly chose to keep AI-written questions and redesign ingestion
around source passage IDs. `passages.py` now builds a trusted table of bounded,
contiguous source windows (at most 800 characters), source-derived labels and
answer snippet IDs. Bedrock selects 1–4 passages and writes exactly two questions
and three wrong options per question. Its private response has `concepts`,
`passage_id`, `first_question`, `second_question`, and, within each question,
`prompt`, `answer_id`, `wrong_option_1`, `wrong_option_2`, `wrong_option_3`.

The provider schema lists the allowed IDs and requires the two question fields
and three wrong-option fields explicitly. Array-size instructions alone did not
produce compliant output in live checks. The server resolves answers, explanation
excerpts, quotes and concept metadata from source records, rotates answer slots,
and prefixes prompts with the source-derived label. It accepts no generated
quotes or private artifact fields. The resulting artifacts pass the existing
full grounding and teaching validators; nothing invalid is silently dropped.

The adapter's optional `response_schema` requests a forced
`submit_structured_response` tool output, with temperature zero. It accepts
exactly one matching input object and `stopReason=tool_use`, then serializes that
object using the JSON library. This is an output envelope only: no tool action,
tool-result message, second inference or automatic retry occurs. AWS documents
this approach for Nova [structured tool responses](https://docs.aws.amazon.com/nova/latest/userguide/tool-choice.html).
Interactive assessment/Tutor calls do not supply this option.

Stored teaching uses the existing authored reading-process guidance explicitly
specified by the new generation contract. This is not a fallback after rejected
output. Runtime Bedrock Tutor personalization is unchanged. PublicCourse,
public questions, sessions and policy/learner contracts are unchanged; the
private ingestion provider format and optional adapter argument changed.
Local/fake generation remains separate.

The final authorized live verification passed using the user's actual calculus
PDF and Nova Lite:

- Upload: HTTP 201; one Bedrock call; four concepts and eight AI-written questions.
- Course ID: `course_e3a8dfeb1d0ec042c153d43e`.
- Session: HTTP 201 with that same course ID.
- First question: `q_1ecbf5a01d3e5171721863be`, verified in the uploaded runtime.
- Public responses contained no Intro AI/admissibility demo content or private
  answer keys, explanations, citation records or generation IDs.

The last three-call approval was fully used; no further cloud call followed the
successful check. Source/model text and credentials were not logged or retained.
This was a real upload/session TestClient verification, not a browser acceptance
claim. Restart the existing dev launcher to load this code, then reupload through
**Upload and start course**. The diagnostic's in-memory registry was isolated
from the browser server and did not persist that course.

Regressions cover source resolution, wrong/foreign IDs, required fields,
ambiguous choices, answer disclosure, exact evidence windows, structured SDK
responses and uploaded Grad Algorithms sessions/turns. Live success proves this
PDF's run, not semantic correctness or guaranteed acceptance of every document.

## Automated verification

Run from the repository root, without live AWS calls:

```sh
MODEL_PROVIDER=fake DYNAMODB_TABLE_NAME= backend/.venv/bin/python -m unittest tests.integration.test_uploaded_course_runtime tests.integration.test_course_sessions tests.integration.test_course_uploads -v
MODEL_PROVIDER=fake DYNAMODB_TABLE_NAME= backend/.venv/bin/python -m unittest discover -s backend/tests/ingestion -v
make check
make smoke
git diff --check
```

`make check` includes integration, runtime catalog, RealAssessor, Tutor,
BayesianLearner, AdaptivePolicy, auth/storage, frontend tests and production build.
The combined integration tests use actual PDF/PPTX fixtures, extraction,
registration, HTTP sessions/turns, assessment, learner, policy and Tutor. Only
provider calls are mocked. They cover correct/incorrect/unsure answers,
progression without repetition, concept transitions, completion, course/session
isolation, missing artifacts after a restart-like condition, malformed artifacts,
policy binding failures, accepted Bedrock personalization and safe fallback.

Recorded results after the activation, timeout and ingestion parsing fixes:
`make check` passed 310 backend tests, all 71 frontend tests,
TypeScript checking and the Vite production build. The separate ingestion suite
passed all 55 tests. `make smoke` passed its actual HTTP demo loop, reset and
preference-isolation checks. `git diff --check` passed. The local Python environment
was synced from the existing lockfile to install missing `python-multipart`;
dependency manifests and locks were not changed. Smoke required permission to
bind its loopback port outside the sandbox. No live AWS calls were made by these checks.

Preflight: fetched origin before edits; branch `main`, HEAD and `origin/main`
both `019894588589b8ce29c7fbf7e5184671748515a0`, ahead/behind 0/0, initially clean.
Before publication, a fresh fetch confirmed that `origin/main` still matched
this base, with no upstream changes to reconcile. Changed paths cover integration wiring, frontend
error handling, regression tests and handoff documentation. Shared public
contracts are unchanged; internal signature additions are described above.
The base is current and the local diff is whitespace-clean. An open-PR/team-task
overlap check was unavailable because this environment has neither `gh` nor a
GitHub connector; the user's statement that prerequisite PRs are merged is the
workstream context. Human review, browser acceptance and remote PR mergeability
are not claimed as completed.

At the activation-fix follow-up, the checkout was already on
`codex/final-uploaded-course-integration` with the same HEAD and the original
integration edits present. Those edits were preserved. Only frontend activation,
its regressions, the synthetic algorithms fixture and this handoff were changed
for the browser failure; backend runtime wiring did not need another fix.

## UI handoff

Start UI work from the latest `main`. Run `make dev` with `MODEL_PROVIDER=fake`
for local UI development without AWS. The synthetic
`backend/tests/ingestion/fixtures/grad-algorithms.pptx` exercises the uploaded-course
path without private course materials.

Preserve the shared onboarding start action: await a successful upload, select
the returned PublicCourse, then navigate to study. Failed or pending uploads
must not create demo sessions. Course title/concepts come from CourseContext's
selected metadata; session creation and reset must send its `course_id`.
Question content comes from the API. Keep the explicit demo entry separate.
`frontend/tests/courses.test.tsx` covers these behaviors.

## Manual Grad Algorithms acceptance

Prerequisites: existing project dependencies (`make setup` if needed), Poppler's
`pdfinfo` and `pdftotext` on PATH for PDFs, and valid AWS credentials already
available to the developer shell. Do not put credentials in repository files.
Stop any existing dev launcher before starting this command; it does not hot reload.

```sh
cd /Users/electricalman/Documents/ChatGPT/MindsAndMachines
MODEL_PROVIDER=bedrock \
AWS_REGION=us-east-1 \
BEDROCK_MODEL_ID=amazon.nova-lite-v1:0 \
BEDROCK_TIMEOUT_SECONDS=12 \
BEDROCK_INGESTION_TIMEOUT_SECONDS=60 \
DYNAMODB_TABLE_NAME= \
make dev
```

Course generation previously inherited the 12-second interactive provider timeout,
which caused observed upload 504s. It now uses a separate 60-second default with a
90-second maximum via `BEDROCK_INGESTION_TIMEOUT_SECONDS`. Only ingestion passes
`purpose="course_ingestion"` to the provider adapter. Assessment and Tutor use the
unchanged interactive timeout and stage/turn deadlines. Both purposes use the
same single-attempt SDK path and cannot extend an enclosing `call_budget`.
Validation remains unchanged: a successful generation can still return 422, with
the safe `course_ingestion_failed reason=...` log identifying the rejected rule.

Open <http://127.0.0.1:5173>. Keeping `DYNAMODB_TABLE_NAME` empty makes this a local
in-memory test. The existing optional sign-in UI may appear first; use the local
preview when Cognito is not configured.

1. In course setup/materials, name the course **Grad Algorithms** and select a real
   text-based Grad Algorithms PDF or PPTX. Use a small lecture excerpt: the
   existing Bedrock ingestion limit is 24,000 extracted characters, 1–8 files,
   at most 20 MB per file. Scanned PDFs need OCR outside this application.
2. Click **Upload and start course** in onboarding. It waits for successful upload
   and activates the returned course before opening Study Desk. Alternatively,
   click **Upload course**, wait for **Course ready**, and click **Start uploaded
   course** or **Activate course**. Upload failure must leave you in setup; it must
   not open the demo. The upload must return 201 before activation.
3. Check that concept labels and the first question are supported by the material.
   Upload validation checks source evidence but does not prove pedagogical
   correctness; review the generated question rather than assuming it is sound.
4. Choose an incorrect answer and click **Check answer**. For a fresh concept,
   check the evidence count changes from 0 to 1 and its mean from 50% to 33.3%.
   Other concepts stay unchanged. Inspect the policy-selected intervention.
5. On valid personalization, the teaching label is **AI-generated teaching**.
   `tutor.teaching_source` is `bedrock`. The backend's safe diagnostic log says
   `tutor_result provider_attempted=True teaching_source=bedrock ... reason=accepted`.
   **Reviewed fallback** means personalization was not accepted and does not pass
   the live-personalization acceptance step. The draft notice remains truthful.
6. Continue to the next question and verify that it belongs to this uploaded
   course, is fresh, and has no Intro AI demo content. Answer more questions to
   exercise concept transitions and final completion. An unsure answer should
   advance without increasing evidence. Reset should preserve the selected course
   while restoring priors.
7. Switch to **Use demo course** separately to check the original demo still works.
   Stop the dev launcher with Ctrl-C when finished.

Ready for this manual test after automated verification. Live AWS access,
accepted generation on the real Grad Algorithms file, and human review of its
educational quality remain manual acceptance items. Course artifacts are still
process-local: restarting the backend requires re-upload, even if sessions were
persisted in DynamoDB. Existing ingestion produces at most four concepts with
two questions each; this is a bounded study bank, not full-course coverage.
