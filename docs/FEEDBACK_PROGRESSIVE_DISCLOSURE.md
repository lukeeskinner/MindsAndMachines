# Post-answer progressive disclosure

Verification date: September 17, 2026. Branch: `codex/feedback-progressive-disclosure`.
Healthy baseline: `2a27b1a`. The interrupted work in `9608ab9` is preserved.

## Change and default experience

The previous reflection screen presented a full evidence table, policy scoring,
next-question preview and repeated concept diagnostics before directing the student
elsewhere for teaching. The new order is result → explanation → posterior change →
next step. Default feedback contains:

- A text verdict derived from the server assessment.
- Up to three complete sentences excerpted from returned Tutor prose. Sentence
  segmentation preserves decimals and math; the full explanation remains in Chatbot.
- The existing Beta plot comparing the prior answer snapshot with the returned
  posterior, current estimate, observation count, and before/current mean when changed.
- A high-uncertainty notice only when reported by backend analytics. An unchanged
  evidence count remains explicit, including unsure and review behavior.
- The next concept, a short contextual explanation, and **Continue** (or **Session recap**).

**See model details** starts closed on each answer. It exposes assessment feedback,
before/current estimates, exact returned interval endpoints (displayed with the
existing one-decimal percentage formatting), interval widths, counts, trusted alpha
and beta, selected intervention, unmodified policy rationale including score
components, next-question context and review eligibility, submitted answer, execution
trace, all concept estimates and teaching preferences. No numeric policy components
are parsed out of prose or recomputed. The duplicated inspector mount from the WIP
was removed.

Completion retains all concept posterior plots, session-start comparisons, evidence
counts, focus ranking and practice actions. The question, chat, flashcard and profile
lifecycle implementations are unchanged.

## Accessibility and layout

The existing Radix disclosure supplies a keyboard-operable button, `aria-expanded`
and `aria-controls`. Enter and Space are tested. Focus moves to the feedback/question
heading using the existing behavior. The graph retains its numerical accessible
label; visible text supplies estimate/count/change and the curve legend. Model details
supply the full comparison table with row/column headers. Collapsing or expanding
never sends an API request. Native buttons retain visible keyboard focus.

Real Chrome screenshots and geometry checks cover 1440, 768, 390 and 320 pixel
widths. The graph and CTA remain within the viewport with no horizontal overflow.
The default view contains one graph and no comparison table or inspector wall.
Reduced-motion mode was used for reproducible browser checks; the existing motion
preferences remain supported.

## Automated verification

`make check` passed with **449 backend tests and 101 frontend tests (550 total)**,
plus TypeScript checking and the production Vite build. Backend suite counts:
integration 101, agents 41, teaching 136, ingestion 95, authentication 10, learner 21,
policy 27, storage 18. Frontend: 11 test files. `make smoke` passed its real HTTP
expanded loop, all three interventions, fresh-question progression, posterior values,
reset and presentation-preference isolation. `git diff --check` passed.

Eight new feedback tests cover default density/visibility, server values, disclosure
keyboard behavior, correct/unclear paths, next-question/remediation transition,
closed details on the next answer, review labeling, missing legacy parameters and
verbatim teaching excerpts. Existing study-flow, uploaded-course and focus-practice
tests were updated for the disclosure and Continue button. Chat, flashcard, focus,
retake and explicit reset regressions continue to pass.

`git diff 2a27b1a -- backend contracts` is empty. Beta–Bernoulli arithmetic, grading,
evidence eligibility, policy/ranking ownership, question pools, trusted identifiers,
provider boundaries and API/storage state handling were not changed.

## Live verification and external blocker

AWS STS succeeded using `AWS_PROFILE=workshop` after the user refreshed credentials.
The app was restarted from the repository root with Bedrock, `amazon.nova-lite-v1:0`,
`us-east-1`, 12-second interactive timeout, 60-second ingestion timeout and memory
storage. Logs contain actual `bedrock_converse_started`, `bedrock_response_received`
and `provider_returned` events. No credentials, prompts or private rubrics are included
in this report.

Six fresh browser upload attempts used `calculus_derivatives_mini_lecture.pdf`.
One returned 201 with four concepts and 15 valid questions. Five returned controlled
422 errors after the existing bounded repair: `insufficient_safe_pool` or
`insufficient_safe_questions`, following invalid/ambiguous generated distractors.
The final four upload attempts all failed validation. The repository fixture is
byte-identical to the supplied PDF in Downloads. Credentials remained valid.
Validation and question pools were not relaxed to obtain a pass.

The successful fresh upload/session run completed all 15 diagnostic questions,
wrong → correct remediation, unsure without evidence, disclosure and exact numeric
comparisons, responsive checks, rich completion and learner-aware chat. The initial
browser harness incorrectly required all coaching to carry a Bedrock teaching label;
backend logs and code established that `authored` is the intended label when an unsafe
generated study tip is dropped and trusted analytics alone are returned. The audit
now verifies the exact returned analytics and source label instead of treating that
safe behavior as a product failure.

The latest complete fresh-upload browser gate remains **blocked by live generated
question validation**. This is an upstream ingestion reliability issue, not a
credential failure, and not evidence that a new upload passed.

To finish independent verification of the final UI, the recovery audit mounts the
actual App and CourseProvider with public metadata from the successful earlier live
upload, then creates a new real API session. It intercepts no network requests and
fabricates no responses. This deliberately skips sign-in/setup/upload and is recorded
as `freshUpload: false`; it is not a substitute for the blocked fresh-upload gate.

Recovery result: **passed** on the final UI, with no console errors or failed HTTP
responses. The new diagnostic session completed 15 questions (four derivative,
four power-rule, three product-rule and four chain-rule questions), with 14 accepted
observations and one unsure response adding none. Two fresh derivative focus questions
continued `Beta(4,2)` → `Beta(5,2)` → `Beta(6,2)`; evidence counts progressed 4 → 5 → 6.
Other concepts remained identical. The top focus changed after these updates.

Chat returned exact trusted estimates, intervals, counts and ranking after a real
Bedrock call; the displayed result was honestly labeled authored when its generated
tip was discarded. Flashcards displayed the returned highest-priority concept,
revealed answers, retained navigation/ratings and made no grading requests. Tied
flashcard priorities retain authored order, whereas focus ranking additionally uses
question availability; the audit respects that existing distinction. Practice Again
returned concepts and session-start values exactly equal to the prior focus results.
Reset made no request until confirmation, then every concept returned to `Beta(1,1)`
with zero evidence. Next questions had empty answer selections and no stale feedback.

Final recovery artifacts are in `/tmp/minds-feedback-recovery-3/`, including
`summary.json`, `turns.json`, `sessions.json`, `chat.json`, desktop/tablet/mobile/narrow
feedback screenshots, model details, completion, focus completion and flashcards.
The fresh-upload failures remain separately recorded. Runtime evidence is in
`/tmp/minds-machines-live.log`; check/smoke logs are
`/tmp/mm-feedback-final-check.log` and `/tmp/mm-feedback-smoke.log`.

## Reproduce

Start the normal live app with the requested environment, then run:

```sh
PLAYWRIGHT_MODULE=/absolute/path/to/existing/playwright \
  node scripts/feedback_browser.cjs
```

The optional harness needs Chrome and `pdftotext`; it does not install dependencies
or run live AWS inside `make check`. `AUDIT_DIR` selects the output directory; the
default is `/tmp/minds-feedback-audit`. JSON responses, screenshots and a summary are
saved outside Git. `AUDIT_EXISTING_COURSE_JSON` explicitly enables the recovery-only
mode with metadata from a previously successful live upload still present in the
running backend registry. It never verifies a new upload.

## Changed paths and handoff

- `frontend/src/App.tsx`: feedback order, teaching excerpt, Continue and disclosure;
  reuse the existing inspector only where visible.
- `frontend/src/components/study/AnswerImpact.tsx`: compact summary, complete advanced
  comparison, next-step text and sentence excerpt.
- `frontend/src/components/study/BetaDistributionPlot.tsx`: optional simple caption;
  posterior curve calculations and other callers retain their previous behavior.
- `frontend/src/style.css`: centered feedback, prominent plot/estimate and narrow layout.
- `frontend/tests/feedback.test.tsx`: eight new regression tests.
- `frontend/tests/study-flow.test.tsx`, `courses.test.tsx`, `focus-practice.test.tsx`:
  disclosure-aware assertions and consistent test posterior parameters.
- `scripts/feedback_browser.cjs`: repeatable live and explicitly labeled recovery audit.
- `README.md` and this report: current interaction and verification/handoff guidance.

Seven-check preflight: assigned feature branch verified; main/origin aligned at the
healthy baseline; changes match the authorized frontend/test/report scope; no shared
contract changes; origin/main is an ancestor with no conflict markers; check and
smoke passed. Open GitHub PR lists were empty at inspection. No main changes, merge,
push, deployment or credential/configuration changes were performed.

Remaining risks: live distractor generation can fail validation; generated coaching
can intentionally fall back to trusted analytics; the browser run covers Chrome, not
all browser/screen-reader combinations. The tutor excerpt preserves returned wording,
including any generic guidance in the existing teaching output. The final fresh
Bedrock upload-to-reset audit must pass before claiming the entire requested live
gate complete.
