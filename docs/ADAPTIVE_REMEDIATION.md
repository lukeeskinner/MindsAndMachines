# Adaptive remediation handoff

This workstream uses one Bayesian learner for question remediation and flashcard
review. No policy weights, assessment grading rules, ingestion generation or
provider adapter were changed. Implementation is on
`codex/targeted-remediation-questions`, based on `ccf082adc51f97bf3cc5608809229dbf1e86cc5c`.

## Audit before implementation

- `teaching/flashcards.py` constructs eight authored demo cards; uploaded cards
  are deterministic projections of stored concept summaries and source filenames.
  There is no runtime flashcard provider path or card database. The processed
  course stores the summaries; the browser stores the current deck and ratings.
- Every card already has `concept_id`. `card_id`, `front`, `back`, and `source`
  complete the display shape. Course/session ownership is supplied by the enclosing
  session response, not independent fields on each card. Course-specific concept
  IDs isolate uploaded decks. No difficulty model, misconception tags or adaptive
  order existed. “Got it” and “Review again” are local self-ratings, not scored recall.
- `Flashcards.tsx` filters topics, reveals answers, navigates and repeats rated
  cards. App keeps it mounted across mode switches, keyed by session ID on reset.
  Previously the deck arrived only at session creation.
- The merged study-mode slice (`ccf082a`) touched flashcards.py, routes.py,
  models.py/api.ts, App.tsx, Flashcards.tsx, flashcards.css, its frontend tests,
  ingestion bank sizing, demo content, docs and integration tests. Ownership spans
  SWE4 teaching/content, SWE3 coordination, SWE1 API/storage/contracts and SWE2 UI.
  This user-authorized slice crosses those seams. GitHub active-PR overlap could
  not be checked because `gh` is unavailable; no remote claim or PR was created.
- RealAssessor grades private server keys, abstains on unsure, and only accepts
  reviewed misconception IDs for three demo question/choice pairs. Uploaded or
  generated questions have no reviewed diagnosis vocabulary and normally return
  `misconception_id=None`. BayesianLearner accepts binary evidence; AdaptivePolicy
  selects from eligible same-concept candidates. RuntimeCatalog exhausts a finite
  concept bank before transitioning. API/storage alone retain session state.
- Tutor renders authored artifacts or bounded, validated Bedrock prose. The
  adapter uses ContextVar deadlines and disables retries. Assessment has 4 seconds,
  Tutor 12, total turn 18, browser 20; upload uses a separate budget. The clean
  shared seam is after assessment/update/selection. Two bounded async tasks fit
  without a coordinator redesign.

## Shared focus and exact trigger

`derive_focus` consumes trusted Assessment plus the learner's evidence-applied
flag. An accepted incorrect answer records course, concept, trusted optional
misconception, triggering question, outcome and answer-key evidence source.
It stores no second copy of mastery or uncertainty. Unscored input preserves an
existing unresolved focus but creates none; a correct answer clears the focus
for that concept. A newer error becomes the current focus. Other weak concepts
still rank using the learner's returned estimates.

Question generation requires **all** of: Bedrock mode, applied scorable incorrect
evidence, a non-null policy decision selecting a fresh question for that same
concept, active uploaded-course grounding, and an unused replacement slot.
Correct/unsure responses, completion, concept transitions, missing grounding and
fake/local mode do not invoke targeted generation. No new mastery threshold exists.

An optional trusted misconception enters both modes. Existing reviewed demo
diagnosis still influences policy and prefers demo-card-6, which explains the
admissibility/consistency distinction. Uploaded courses currently have no reviewed
misconception/card mapping: they use valid concept-level remediation. Tests inject
a trusted assessor result to verify that a future reviewed diagnosis reaches the
generator; no production diagnosis is invented.

## Questions, authority and storage

`TargetedQuestionGenerator` calls the existing `provider.complete` abstraction at
most once with a strict structured-output schema. It receives only active-concept
source references from the active course, prior server question/key/rubric,
submitted answer, trusted assessment/focus and existing prompts. The server assigns
an exact source answer, preferring a complete sentence different from the prior
answer where possible. The model returns only a prompt and three distractors.
Server code inserts the assigned answer, grading key, reference and rubric, mints
a unique ID, assigns course/concept and supplies the reserved non-correct unsure
option. Model output cannot set grading or source authority, session, course,
concept, focus, policy or estimates.

The diagnostic log `targeted_question_result reason=...` reports acceptance,
timeout, provider failure or validation rejection without logging source text,
private answers, prompts or raw exceptions.

Validation rejects extra/duplicate JSON fields, non-JSON constants, invalid types,
empty/oversized text, duplicate choice IDs/text, invalid keys, foreign references,
negative questions, answer text in stems, normalized duplicate prompts, trigger
repetition, control IDs/markers and recognizable demo contamination. The correct
choice must be an exact complete source sentence or quote of at least three words;
the rubric must equal the cited quote. Distractors appearing in that quote fail.
This is conservative extractive grounding, **not proof of semantic correctness**:
question/answer relevance and the falsity of paraphrased distractors still require
educational review. It does not generate arbitrary new worked math problems.

Each generated question replaces the policy's selected fresh bank slot only for
this session. Stored metadata records the original slot and private provenance.
On subsequent requests, the API applies that session's overlay to a new runtime
catalog, preserving bank position and candidate identity while redirecting all
candidates for the replaced slot. Consumed IDs include the generated question.
The number of available questions stays finite and the public question count
remains accurate. The processed course and global demo catalog are untouched.
RealAssessor grades the stored generated key next turn without needing a provider;
BayesianLearner and AdaptivePolicy continue unchanged. Memory and mocked Dynamo
round-trip tests cover private state; legacy Dynamo records default empty fields.

The demo has no equivalent source-reference registry, so it retains authored
fresh questions. Generated questions are not reusable across sessions or courses.

## Flashcards and frontend

Cards remain existing course-grounded content; there is no new card generation.
Stable lexicographic ranking puts the unresolved focus concept first, then a
reviewed misconception-specific card within that concept, then lower existing
mastery mean. Ties preserve authored order. No statistical score or intervention
formula is introduced. Missing misconception-specific cards fall back to concept
ranking; missing estimates/ties preserve existing order. Course decks are built
from the active course only, with a private demo-only card tag map.

TurnResponse now carries ordered cards using the unchanged Flashcard shape.
App forwards the list; when card content/order changes, the existing component
refreshes order and hides any revealed answer while retaining self-ratings and
topic filter. An identical deck preserves position and revealed state. Merely switching
modes preserves position. Reset creates a fresh session/deck. No card interaction
submits an assessment or changes mastery. No new labels or UI redesign were added.
Question UI and public Question shape are unchanged. Existing assessment fields,
including its explicitly public diagnosis, remain unchanged; no new hidden focus,
keys, rubrics, provenance, prompts or ranking values are exposed.

## Deadlines and fallback

After assessment/update/policy, generation (8 seconds) runs concurrently with
Tutor (12 seconds). Both inherit the remaining 18-second turn budget, and provider
configuration may shorten their waits. Assessment plus parallel waits stays at
most 16 seconds. Each stage makes at most one call, with no retries or fallback
provider. Invalid/failed/timed-out generation returns the existing policy question;
the card order still reflects the accepted evidence. Tutor authority is verified
against the original decision before substituting the validated question content.
Total-turn cancellation cancels pending generation and saves no partial state.
Late SDK threads cannot write session state.

## Changed files and review risks

- `backend/app/teaching/remediation.py`, `targeted_questions.py`: shared focus,
  ranking and bounded generation/validation; `runtime_catalog.py`: session overlay.
- `backend/app/agents/coordinator.py`, `api/routes.py`, `main.py`: turn integration.
- `backend/app/storage/memory.py`, `dynamo.py`: private state and compatibility.
- `contracts/models.py`, `api.ts`, `fixtures/turn_response.json`: additive card list.
- `frontend/src/App.tsx`, `components/study/Flashcards.tsx`: accept server ordering.
- `backend/tests/teaching/test_remediation.py`, `tests/integration/test_remediation.py`,
  `backend/tests/storage/test_dynamo.py`,
  `tests/integration/test_uploaded_course_runtime.py`,
  `frontend/tests/adaptive-flashcards.test.tsx`: new coverage and updated expectations.
- `README.md`, `docs/CONTRACTS.md`, this handoff: behavior and contract documentation.

Review the cross-owner integration and additive response field together. The most
important merge risks are concurrent edits to routes/coordinator/contracts/App,
changed fresh-slot semantics in the session catalog, and generated-content quality.
Sequential submissions and existing session security remain baseline assumptions.
Live AWS, manual browser walkthrough and active remote PR overlap are unverified.
The final-review request authorizes a scoped commit and branch push after passing
checks. No merge, deployment or live AWS calls are part of this work.

## Final scope and semantic review

Git reports 21 files: 15 modified tracked files and 6 new files. All match the
approved file list above. Twenty were edited with the patch tool; the response
fixture was edited by a Python command. This likely explains the earlier UI
summary of 20, although that historical counter cannot be independently verified.
Git's complete list includes the fixture. Virtualenv, node_modules and build
output are ignored and excluded from staging; no environment/cache files or
dependency lockfile changes belong to the commit.

The review found and fixed one regression within the approved flashcard files:
resending identical cards reset browsing/reveal state. The new regression test
failed before the fix and passes with unchanged decks preserving their state.
No new product functionality was added. Further tests exercise consecutive
session-local replacements, checking answered history, retained grading keys,
source provenance and consumed-ID filtering. Failure tests compare the fallback
question, decision and learner estimates with the exact deterministic turn result.

## Verification results

- Targeted remediation/shared flashcard checks: 12 tests passed. These cover the
  uploaded end-to-end flow, subsequent trusted-key grading and Bayesian update,
  isolation, validation failures, trigger exclusions, parallel execution,
  cancellation, persistence, reviewed misconception preference and concept fallback.
- The focused backend run passed 167 tests: 12 remediation, 9 uploaded-course
  runtime, 22 RealAssessor, 21 BayesianLearner, 27 AdaptivePolicy and 76 Tutor.
  Both flashcard frontend test files passed all 6 tests separately.
- `make check`: passed, including 379 backend tests (73 integration, 41 agents,
  136 teaching, 56 ingestion, 10 auth, 21 learner, 27 policy, 15 storage), frontend
  TypeScript/build and 77 frontend tests across six files. This includes
  RealAssessor, BayesianLearner, AdaptivePolicy, Tutor, uploaded-course integration
  and flashcard coverage. The existing flashcard test file is unchanged.
- `make smoke`: passed against the actual temporary local HTTP server, using fake
  providers. The initial sandbox run could not bind loopback; the permitted rerun
  passed. No AWS calls occurred.
- `git diff --check`: passed. Pre-commit HEAD and fetched origin/main were
  `ccf082a`, 0 ahead / 0 behind; only this workstream's 21 files were changed.
- Dependency setup used the existing frontend lockfile without modifying it.
  npm reported a pre-existing Node engine mismatch (Node 24.14 versus jsdom's
  requested 24.15+ on that major). The build/tests nevertheless passed. Existing
  large-bundle and jsdom scrollTo warnings remain non-failing.

Seven-check preflight: assigned branch verified; origin fetched/current at task
start; paths reviewed against this authorized cross-owner slice; shared-contract
changes explicitly reported; no local conflict markers/diff errors (remote PR
mergeability unverified); check passed; HTTP smoke passed. Active-team overlap and
a manual browser walkthrough remain unverified. Ready for code review, with
educational review of generated content and the cross-owner seams called out above.
