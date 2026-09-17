# Live Calculus demo verification

The real browser → upload API → Bedrock → course session → assessment → Bayesian
learner → adaptive policy → Tutor → remediation → browser flow passed. The app
was left running on frontend port 5173 and backend port 8000, using local profile
`workshop`, region `us-east-1`, model `amazon.nova-lite-v1:0`, interactive timeout
12 seconds, ingestion timeout 60 seconds, and in-memory storage.

No commits, pushes, merges, deployments, credential files, or dependency changes
were made by this debugging session. Existing uncommitted work was preserved.

## Root causes and fixes

- Credentials were available only through the named `workshop` profile. The
  default agent shell had none. AWS and loopback access also required execution
  outside the local sandbox. STS succeeded with that profile.
- An unconstrained generation request covering 30 source passages could collapse
  the lecture to one generic topic and repeated questions. The server now selects
  explicit numbered topic sections when available and requests two named question
  slots per section, capped at five sections. Unstructured sources retain the
  existing plan path.
- Nova sometimes associated a prompt with the wrong source answer when asked to
  infer mappings from passage IDs or numeric repair paths. Each named slot now
  carries its own topic and exact assigned answer in the schema. Repair payloads
  also pair each target directly with its source and answer.
- Generating only wrong options sometimes caused Nova to include another correct
  statement. Named slots now include an exact `assigned_answer_echo`, so the model
  sees the complete MCQ shape. Code validates that echo against the trusted source,
  rejects any mismatch, discards the echo, and inserts the server-owned answer.
  Generation instructions explicitly prohibit true paraphrases as distractors.
- Source-overlap validation previously missed capitalization, terminal punctuation,
  and true statements elsewhere in the same concept. Checks now cover the whole
  concept passage case-insensitively and ignore terminal prose punctuation while
  preserving mathematical operators. Regression tests cover a formula ending in
  a period versus a source colon, and distinguish `n-1` from `n+1`.
- A derivative-specific example in generic repair instructions could be copied
  into other topics. It was replaced with topic-specific instructions.
- Added safe accepted-course counts to logs and a fixed diagnostic code for a
  concept left without safe questions.

The independent-slot pipeline remains: generate → validate → preserve valid
slots → at most one targeted repair → revalidate → discard remaining invalid
slots only when every concept remains usable. No validator was disabled.

## Final live results

Input: `calculus_derivatives_mini_lecture.pdf`, uploaded through the React UI in
headless Chrome using the real Vite proxy and FastAPI endpoints. No API or
provider responses were mocked. Login used the app's explicitly labeled local
preview access, not Cognito.

| Check | Observed result |
| --- | --- |
| Frontend/backend availability | Both HTTP 200 |
| PDF upload | `POST /api/v1/courses` → 201 |
| Course session | `POST /api/v1/sessions` → 201 |
| Course count | One uploaded course |
| Concepts | Four: instantaneous rate of change, Power Rule, Product Rule, Chain Rule |
| Questions/cards | Six accepted questions; four source-derived flashcards |
| Generation | Two Bedrock calls: initial generation and one repair |
| Repair/discard | Zero successful repairs; two rejected slots discarded |
| Rejection reasons | Product Rule second slot: invalid choices; Chain Rule second slot: ambiguous choice |
| Incorrect answer | HTTP 200, `incorrect`, fresh generated remediation for the same weak concept |
| Policy | `diagnostic_probe`, selection priority 0.7215 |
| Tutor | Accepted Bedrock teaching, `fallback=false`, labeled draft course guidance |
| Correct remediation | HTTP 200, `correct`; trusted generated answer key used by RealAssessor |
| Flashcard priority | Derivative card first after first error; Power Rule moved from second to first after a later Power Rule error |
| Reset | HTTP 201, new session, same course, all priors restored |
| Completion audit | All six bank questions traversed through the real API; unsure responses added no evidence; clean completion |
| Browser errors | No uncaught page errors in the successful browser run |

The first concept changed as follows; the other three concepts remained at their
priors during the two-answer remediation sequence:

| State | Mean | 90% interval | Evidence |
| --- | --- | --- | --- |
| Initial | 0.5 | [0.05, 0.95] | 0 |
| Incorrect answer | 0.3333333333333333 | [0.0253, 0.7764] | 1 |
| Correct generated remediation | 0.5 | [0.1354, 0.8646] | 2 |

The remediation asked about the instantaneous rate of change at a point; its
trusted source answer described `f'(x)` and tangent slope. The later Power Rule
question asked about differentiating `x^n`. Cards quote the uploaded Calculus
material and name its PDF; no Intro AI concept IDs or fallback questions appeared.
Each turn reported `assess`, `update`, `select`, `teach`.

The final server log records configured model `amazon.nova-lite-v1:0`, actual
`bedrock_converse_started`, `bedrock_response_received`, and `provider_returned`
events. Ingestion calls took 6704.0 ms and 2001.0 ms. The first incorrect turn
recorded successful assessment, Tutor, and targeted-generation calls, with
`tutor_result ... teaching_source=bedrock ... reason=accepted` and
`targeted_question_result reason=accepted`. Eleven successful Bedrock responses
were recorded across the final browser run and subsequent completion audit.
Authored concept-transition/completion messages remain honestly labeled authored.

## Verification

- `make check`: PASS — 414 Python tests (77 integration, 41 agents, 136 teaching,
  87 ingestion, 10 auth, 21 learner, 27 policy, 15 storage), TypeScript check and
  Vite build, 77 frontend tests across six files.
- Targeted ingestion suite: PASS — 87 tests, including strict source-answer echo,
  named-slot binding, repairs, partial acceptance, and ambiguity regressions.
- Targeted partial-generation suite: PASS — 11 tests.
- `make smoke`: PASS — real HTTP loop, all three interventions, fresh questions,
  posterior values, reset, and preference isolation. Its initial sandbox bind
  failure was rerun successfully outside the sandbox.
- Live Chrome walkthrough: PASS — upload, session, wrong answer, remediation,
  flashcards, correct answer, second-topic prioritization, reset.
- Full public-bank completion audit: PASS — six questions, unchanged priors for
  unsure responses, clean course completion.
- `git diff --check`: PASS.
- `git fetch origin`: PASS; `HEAD...origin/main` remains `0 0` at `b6bf99d`.
  Work stayed on the existing `main` checkout under the task's explicit authority;
  no branch switch, merge, or simulated merge was performed.

The frontend tests print jsdom's existing `scrollTo` not-implemented notices;
they pass. Public API contracts and the four domain interfaces were unchanged.
The named ingestion response and exact-answer echo are internal provider-protocol
changes, with their resolution and regression tests updated together.

## Files changed by this debugging session

- `README.md`
- `backend/app/api/courses.py`
- `backend/app/ingestion/README.md`
- `backend/app/ingestion/passages.py`
- `backend/app/ingestion/pipeline.py`
- `backend/app/teaching/targeted_questions.py`
- `backend/tests/ingestion/test_passages.py`
- `backend/tests/ingestion/test_partial_generation.py` (already untracked on entry)
- `docs/LIVE_DEMO_REPORT.md` (this report)

Other working-tree changes below predate this session and were preserved.

## Evidence files

Temporary local evidence is available at:

- `/tmp/minds-machines-live.log` — all live attempts, restarts and safe diagnostics.
- `/tmp/minds-live-browser.log` — final browser assertions and public responses.
- `/tmp/minds-live-evidence/` — public JSON responses and browser screenshots,
  including `incorrect-feedback.png`, `correct-feedback.png`, and `moved-flashcard.png`.
- `/tmp/minds-check-final.log`, `/tmp/minds-targeted-final.log`,
  `/tmp/minds-partial-final.log`, `/tmp/minds-smoke-final.log`.
- `/tmp/minds-bank-audit.log` — public bank and successful completion.
- `/tmp/minds-live-browser.cjs`, `/tmp/minds-audit.py` — local verification scripts.

These files are temporary and were not added to the repository.

## Remaining demo risks

- The requested two-answer live scenario passes. Generated educational content
  still needs human review: lexical checks do not prove semantic uniqueness.
  For example, the stored derivative question's “slope of the curve” distractor
  can be interpreted as tangent slope; wording about multiplying a constant
  coefficient by the exponent can also be read ambiguously. The successful
  first remediation replaced that derivative bank slot with a fresh question
  whose alternatives were average, total, and maximum change. Do not present the
  complete generated bank as pedagogically certified.
- Safe discards can leave only one question for a concept (Product and Chain
  Rule in the final upload). Such a concept transitions after its sole question;
  fresh remediation requires an available same-concept slot.
- Tutor guidance remains conservative source/process guidance, with a draft
  label; it does not promise independently generated worked solutions.
- AWS credentials expire; provider latency/quality can vary. Failed generation
  remains bounded and retains the original safe question when possible.
- Sessions and uploaded courses are in memory and disappear on restart. Reuploading
  identical title/source with different generated content can conflict with the
  existing immutable course registration; use a fresh title or restart the app.
- Cognito login, DynamoDB persistence, deployment, multi-user concurrency, and
  real learner outcomes were not part of this verification.

## Final working-tree status

```text
 M README.md
 M backend/app/api/courses.py
 M backend/app/ingestion/README.md
 M backend/app/ingestion/models.py
 M backend/app/ingestion/passages.py
 M backend/app/ingestion/pipeline.py
 M backend/app/teaching/targeted_questions.py
 M backend/tests/ingestion/helpers.py
 M backend/tests/ingestion/test_ingestion.py
 M backend/tests/ingestion/test_passages.py
 M backend/tests/ingestion/test_teaching.py
 M docs/ADAPTIVE_REMEDIATION.md
 M frontend/package-lock.json
 M frontend/src/lib/courses.ts
 M frontend/tests/courses.test.tsx
 M scripts/dev.py
 M tests/integration/test_course_uploads.py
 M tests/integration/test_dev_launcher.py
 M tests/integration/test_remediation.py
 M tests/integration/test_uploaded_course_runtime.py
?? backend/tests/ingestion/test_partial_generation.py
?? docs/LIVE_DEMO_REPORT.md
?? package-lock.json
```
