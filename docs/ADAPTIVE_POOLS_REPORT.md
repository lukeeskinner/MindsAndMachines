# Adaptive pools hardening

## Baseline reproduction, before implementation

Inspected clean branch `codex/adaptive-pools-posterior-viz` at `3371e11`.
Fetched origin: `origin/main...HEAD` was `0 0`. Workshop STS succeeded.
The current user request authorizes this post-G1 slice across module ownership;
older G1 restrictions in the repository are historical for this task.

A fresh real Bedrock browser upload of `calculus_derivatives_mini_lecture.pdf`
returned 201 and created a four-concept, eight-question course. It had two
questions per concept, not one. A wrong derivative answer changed Beta(1,1) to
Beta(1,2), mean 1/3, interval [0.0253,0.7764], count 1. Remediation returned a
different question about tangent slope. Flashcards showed four cards, one per
concept. New session/reset returned zero evidence and the identical first item.

Root causes and limits of the initial claims:

- Fixed-topic generation requests only two slots and selects the numbered
  definition block, excluding nearby examples/comparisons. Partial acceptance
  allows a concept to shrink to one question after one repair.
- Runtime eligibility already excludes consumed IDs (including unsure), and
  concurrent writes are rejected. Exact within-session ID repetition is not
  established by the observed baseline. Content equivalence is less protected:
  ingestion compares case-folded whole items; remediation checks exact normalized
  stems. Neither establishes semantic independence.
- The scheduler exhausts one concept in artifact order. AdaptivePolicy selects
  the intervention, but course coverage/order does not use learner uncertainty.
- The learner consumes every accepted binary assessment without item identity;
  upstream eligibility is therefore the critical evidence boundary.
- All learner state lives inside Session. Session creation always initializes
  Beta(1,1); Practice again calls exactly that route. No cross-session evidence
  ledger or recent-item history exists.
- Completion counts client journal entries as questions and sums all current
  concept evidence. The latter works only because every session starts at zero;
  it would mislabel lifetime evidence after adding persistence. No explicit
  unique-item or accepted-this-session metrics exist.
- Flashcards project one entire concept summary. Ratings are local and do not
  update the learner, which is correct.
- Public estimates omit alpha/beta. The UI has interval bars and text, with no
  density curves. Completion only lists changed concepts and raw values.

The current generic protocol and the earlier runtime audit are documented below.

## Architecture and behavior delivered

Course content stays immutable. Numbered definition passages also retain their
same-source worked example and application blocks. The known Calculus bank requests
**4 question candidates and 3 cards per concept** (up to 16/12 total): definition,
rule/interpretation, worked application, and purpose. Generation remains one
initial call plus at most one repair, preserving valid slots. Rich topics reject
below three safe items per concept; narrow legacy documents keep the existing
smaller-bank path.

The final production protocol has **no source-specific or subject-specific
question recipes**. The earlier authored Calculus experiment was removed after
the user's architectural correction. Generic slots bind to exact source
statements. Numbered sections gather adjacent same-chunk blocks without matching
their names; unnumbered fact-rich passages use the same protocol.

An attempted generic writer + independent Nova semantic reviewer was not adequate:
the live trial approved both the assigned power-rule formula and the same formula
as a distractor; it also admitted a tangent-slope paraphrase beside the assigned
derivative definition. Four calls yielded 12 items but did not establish safety.
That reviewer was removed from production, rather than used as false assurance.

The implemented deterministic alternative is **explicit exact-source recall**.
For each distinct source statement, trusted code supplies a quoted prefix and the
prompt asking which ending completes that original statement exactly.
The source answer remains server-owned; the model supplies three alternative
endings and echoes the assigned answer without authority to change it. The
schema and validator enforce the generic prompt. Existing source, negative-stem,
answer-leakage, answer-reference, ambiguity and duplicate validators still run.
An additional all-upload source check rejects distractors that are exact source
statements elsewhere. Four candidates are requested per rich concept; at least
three must survive one bounded repair. No unsafe candidate is inserted to fill
a quota.

This deliberately changes the assessment family from free-form application MCQs
to source recall for rich pools. It guarantees a literal source-completion task,
**not arbitrary factual truth, independent knowledge, application mastery, or
universal semantic equivalence detection**. Prompts visibly say Source recall;
metadata and README state the limitation. Source truth remains unverified.
Sparse legacy documents keep their earlier limited path rather than pretending
to support a three-item pool. Unsupported extraction still fails honestly.

API storage now owns a LearnerProfile separate from Practice Session. The profile
stores Beta state, exposure fingerprints, recent items and active session; the
session stores progress, history/chat, current item, remediation, budget and a
start snapshot. Memory saves detached state; Dynamo saves profile+session in one
transaction with consistent reads. Practice again carries the profile via
previous_session_id, retires the old session and clears transient state.
Explicit reset_learner clears beliefs and exposure history only after the UI's
second deliberate click. No credentials, student records or runtime database
were added.

PracticeSelection owns evidence collection; AdaptivePolicy still owns the
intervention. It chooses without replacement, prioritizes lifetime-unseen items,
provides one immediate different same-concept question after a wrong answer,
covers concepts with fewer than two questions first, then weighs mastery gap
plus interval width. Stable ties rotate by session and recent use. The budget is
bounded by bank size and concept count; four concepts yield ten questions.
This prevents a single weak concept starving the others. Budget exhaustion
completes predictably without requiring all 16 items.

When the lifetime bank is exhausted, previously exposed items are visibly review
and supply **zero** new observations. They still receive assessment and teaching.
There are no identical repeats within the current session. Rich pools do not
invoke the existing slot-replacement generator as unbounded replenishment;
legacy smaller courses retain bounded targeted generation. IDs, normalized
prompt/choice content and distinct bound source statements protect item
identity; arbitrary semantic equivalence remains a documented limitation.

Counts have separate meanings: submitted_answers is saved successful turns;
unique_questions_seen is distinct IDs issued this session (including next-item
preview); accepted_observations is evidence_applied entries this session.
Concept evidence_count remains accumulated profile evidence. Unsure, chat,
flashcard flip/rating and review are not Bernoulli observations. Duplicate/stale
POSTs are rejected. The profile lock also rejects retake/reset during an active
chat or turn; superseded session writes return 409.

Flashcards use three different exact source excerpts (core idea, source detail,
source connection), with stable content IDs. Ranking uses the same posterior. New evidence
reranks weak concepts and rotates within a concept when the displayed card would
repeat; retakes rotate their initial cards. Self-ratings stay local.

The Beta mathematics are unchanged. Contracts now expose alpha, beta, mean,
interval90 and evidence_count. Lightweight React/SVG plots show probability 0–1,
density, mean marker and 90% interval, with accessible exact text. They use
log-factorial density calculations and finite-value tests, not inferred rounded
parameters or image generation. Sidebar plots and a selected larger plot update
from the response. Answer feedback compares before this answer to now.
Completion shows **all concepts**, dashed session-start and solid current
curves on the same vertical scale within each plot, with numerical details
secondary. Density heights are explicitly scaled per plot; heights across
different plots must not be compared.

## Bugs reproduced and fixed

- Two-slot generation and one-slot partial acceptance limited evidence diversity.
- Nearby source examples/applications were omitted from fixed-topic assignments.
- Semantically true distractors survived literal overlap checks in live Nova output.
- Smaller failed slots needed a minimum-three gate for rich demo pools.
- Punctuation/choice-order changes could evade whole-item duplicate matching.
- Session-owned beliefs reset on every normal retake; no exposure ledger existed.
- Retakes replayed the same first question; old sessions could remain usable.
- Completion conflated current accumulated evidence with session evidence.
- One-card concept projection and reranking could repeat the displayed card.
- Estimates lacked trusted distribution parameters and summary curves.
- A first attempted answer-only evidence fingerprint incorrectly conflated different
  graph problems with the same classification answer; regression preserved
  prompt/content identity instead.
- A short phrase matched an earlier source recipe outside its intended context.
  The entire recipe mechanism was subsequently removed from production.
- Independent model review admitted semantically correct distractors. It was removed
  from production in favor of explicit, deterministically checked source recall.
- A quoted negative source clause triggered the unchanged forbidden-stem validator;
  cue selection now shortens the exact prefix before that clause.
- Dynamo reads now explicitly request consistency alongside atomic profile/session
  saves to avoid reading stale progress immediately after a write.

## Historical browser audit before generic-protocol correction

This establishes the retained runtime behavior, not final generation proof.
The source-specific generation behind this run has been removed.

Real browser upload: **201**, session: **201**. Runtime logged four concepts,
16 questions, one provider call, zero repairs/discards (13.054 seconds).
No Intro AI content appeared. Question IDs and visible prompts were recorded
before submission. D/P/R/C below mean derivative, power, product, chain.
All other concepts retain their previous values in each row.

| # | Question ID | Visible prompt (after concept prefix) | Outcome | Updated concept Beta; mean; 90% interval |
|---|---|---|---|---|
| 1 | q_58ce5e8e1161f9df62091b34 | Why is an instantaneous derivative useful for continuously changing quantities? | wrong | D (1,2); 33.3%; 2.5–77.6% |
| 2 | q_6022f143eb1510546d9da282 | Which interpretation connects f'(x) with the graph of y = f(x) at a single point? | correct | D (2,2); 50.0%; 13.5–86.5% |
| 3 | q_1daa205e53591563a0b39747 | What computational advantage does the power rule provide? | unsure | P unchanged (1,1); 50%; 5–95% |
| 4 | q_3cd965a0e3a7d71b9b83d524 | Which worked calculation correctly differentiates h(x) = x^2 sin(x)? | correct | R (2,1); 66.7%; 22.4–97.5% |
| 5 | q_063703b3612a48e7c114c408 | Which worked calculation correctly differentiates y = (2x + 3)^4? | correct | C (2,1); 66.7%; 22.4–97.5% |
| 6 | q_7c4b16072be86ef94404a14b | When differentiating a constant multiple c·x^n, what happens to the original constant factor c? | correct | P (2,1); 66.7%; 22.4–97.5% |
| 7 | q_651b62489cf1be331a9caf16 | Which expression correctly differentiates h(x) = u(x)v(x)? | correct | R (3,1); 75.0%; 36.8–98.3% |
| 8 | q_0df5bdd31b9fdd2e45f1486b | Which procedure correctly differentiates y = F(g(x))? | correct | C (3,1); 75.0%; 36.8–98.3% |
| 9 | q_6c3c68ef3d1bcd2f3bb01ddc | For s(t) = t^2 meters, which account correctly connects average velocity near t = 2 with instantaneous velocity at t = 2? | correct | D (3,2); 60.0%; 24.9–90.2% |
| 10 | q_b0ca62b78764273bbc72db0c | Which calculation correctly applies the power rule to f(x) = 7x^5? | correct | P (3,1); 75.0%; 36.8–98.3% |

Ten distinct IDs and stems, no repeats, all four concepts covered, **10 answers /
10 unique / 9 accepted observations**. The wrong→fresh same-concept→correct
sequence changed derivative interval width 90.0→75.1→72.9 percentage points.
Plots were inspected visually; four comparison panels showed the exact same
values as the accessible text. Mean markers, broad initial distributions and
current density/intervals were visible.

After question 1, Chatbot returned real Bedrock prose about instantaneous change,
f'(x) and s(t)=t². Quiz→chat→flashcards→quiz retained the pending next item and
beliefs. The 12-card deck prioritized derivative, then presented three distinct
grounded cards (definition, tangent interpretation, velocity example). Flipping
and both ratings left all four posterior strings exactly unchanged.

Practice again started at zero progress with unused
q_bb06b911e680d6a925ebf574 (instantaneous-rate definition), no selection/feedback,
empty chat and exact unchanged final beliefs D(3,2), P/R/C(3,1).
The first reset click only opened confirmation and preserved beliefs. The second
click restored all four Beta(1,1), zero evidence, 5–95% intervals and a fresh
session. Browser console had no warnings/errors in the audited flow.

## Final verification and review limits

The final generic regression uses **unnumbered resonator notes** with four facts,
then changes the filename from PPTX to PDF. Provider payload and schema are
identical. Tests reject changed stems, changed answer echoes, alternative exact
source statements, and insufficient pools after one failed repair. A production
source scan asserts absence of Calculus subject strings and recipe dependencies.
The source cue is shown only in the prompt; options contain missing endings,
so prefix matching alone does not reveal the key. A regenerated source fact with
new distractors has the same evidence fingerprint.

Targeted ingestion, pool/scheduler/retake, learner, remediation, storage, flashcard,
chatbot and frontend tests run inside make check; focused source-protocol,
adaptive-pool and posterior tests also passed independently. Final suite counts:
integration 90, agents 41, teaching/remediation 136, ingestion 95, auth 10,
learner 21, policy 27, storage 18 (**438 Python tests**); frontend **86 tests**,
including four posterior tests. TypeScript/Vite production build passed.
make smoke passed actual HTTP turn, posterior, retake/reset and preference checks.
git diff --check passed. Build output retains pre-existing dependency
"use client"/source-map warnings; the test environment reports unsupported
window.scrollTo, with no test failures.

MVP preflight: stayed on codex/adaptive-pools-posterior-viz; fetched origin and
confirmed origin/main...HEAD was 0 0 before the feature commit; all paths belong
to this explicitly authorized cross-module task; shared Python/TypeScript
contracts and golden fixture changed together and require reviewer attention;
no conflict markers/diff whitespace issues; make check and HTTP/browser smoke
performed. Remote PR mergeability and independent human review are unverified
(no PR created or main merge requested). No push, deployment or protection change.

Remaining limits:
- Source recall is intentionally narrower than application mastery. It does not
  establish whether arbitrary source claims are true. General application MCQ
  generation still needs a stronger semantic-validation or reviewed-content seam.
- Generic grouping is bounded and heuristic; not every document yields enough
  distinct extractable facts. Rich concepts fail below three accepted items.
  OCR and oversized material remain outside the current ingestion contract.
- Finite banks eventually become labeled review and supply no new evidence.
  No unlimited provider replenishment was added.
- Anonymous profile continuity requires its previous-session handle. Memory
  persistence lasts for the backend process. Browser reload/account recovery and
  durable course recovery are not newly implemented.
- Dynamo serialization, consistency and transaction behavior are tested with
  injected tables; a live Dynamo table was not provisioned or exercised.
- Write exclusion is single-process. No distributed multi-worker locking claim.
- Beta confidence is an experimental item-response model. Distinct source facts
  are not a proof of statistical independence; teaching may also affect performance.
- Curves are finite and analytically tested across uniform and concentrated
  integer posteriors. Density heights are scaled per plot and explicitly labeled.


## Final generic-protocol live rehearsal

After the final code changes and full checks, restarted a clean backend
(pid 38703) and freshly uploaded the Calculus PDF through the browser.
**Upload 201; session 201.** Initial call took 15.133 s; one repair took 1.800 s.
An invalid duplicate-choice product-rule candidate remained invalid after repair
and was discarded. Final bank: **15 questions, four concepts: derivative 4,
power 4, product 3, chain 4; 12 cards, three per concept**. No fallback bank or
demo-only content was substituted. This is the final generation proof.

Every prompt used the generic template:
“<concept>: Source recall: Which ending completes the quoted statement
«<cue> …» using its exact original wording?”
Only missing endings appear as options. The exact visible cues and IDs follow.
Outcomes and after-answer distributions were recorded from the rendered DOM;
unaffected concepts retained their preceding state.

| # | Question ID | Concept / exact cue | Outcome | Updated Beta |
|---|---|---|---|---|
| 1 | q_06e0f6cfe499a1a6c5eec561 | Derivative / Derivative as Instantaneous Rate of Change Definition A derivative | incorrect | (1,2), 33.3%, interval 2.5–77.6%, n=1 |
| 2 | q_07ab5f56f5ab7ab75cd7bf31 | Derivative / Concrete example Suppose s(t) = t^2 meters. From t = 2 to t = 2.1, average velocity is [s(2.1) - | correct | (2,2), 50.0%, interval 13.5–86.5%, n=2 |
| 3 | q_160c626f75174d7c60fbc09a | Power / Power Rule Definition For f(x) = x^n, the power rule gives f'(x) | unsure | unchanged (1,1), n=0 |
| 4 | q_25790e7b4feb5333f38fbe7b | Product / Why it matters Differentiation does | correct | (2,1), 66.7%, interval 22.4–97.5%, n=1 |
| 5 | q_101a46058cff80c749a04675 | Chain / Why it matters Compositions appear in powers, trigonometric functions, exponentials, logarithms, and | correct | (2,1), 66.7%, interval 22.4–97.5%, n=1 |
| 6 | q_1c4205ec34afd21c475d9707 | Power / Constant coefficients | correct | (2,1), 66.7%, interval 22.4–97.5%, n=1 |
| 7 | q_b8747f188aa1021e703be99b | Product / Each factor is differentiated once | correct | (3,1), 75.0%, interval 36.8–98.3%, n=2 |
| 8 | q_2502b8faff9479a187cd6475 | Chain / Chain Rule Definition The | correct | (3,1), 75.0%, interval 36.8–98.3%, n=2 |
| 9 | q_377f8535dd7843393b7dc726 | Derivative / Why it matters Many quantities change continuously. Average speed describes an interval, while a derivative gives | correct | (3,2), 60.0%, interval 24.9–90.2%, n=3 |
| 10 | q_1d88477eb70405c536435271 | Power / Concrete example If f(x) = 7x^5, then f'(x) = 7(5x^4) = 35x^4. | correct | (3,1), 75.0%, interval 36.8–98.3%, n=2 |

Audit assertions: ten unique IDs, ten unique prompts, no back-to-back or later
repeat, fresh derivative item after the wrong answer, all concepts covered.
Completion displayed **10 questions answered / 10 unique / 9 accepted**.
The recap rendered four start/end comparison plots with exact values and clear
density scaling. Uniform priors, changed means and narrowed intervals were visible.

Weak derivative came first in the 12-card deck. Three successive cards contained
its definition, tangent interpretation and application context; content was
different and source-grounded. Flips/ratings left all posterior strings unchanged.
Quiz navigation retained q_07ab5f56f5ab7ab75cd7bf31 across card review.

The final real Chatbot response explained inner/outer functions and
dy/dx = F'(u)g'(x), labeled AI-generated. Beliefs were exactly unchanged on
returning to quiz; no Intro AI contamination appeared in the uploaded course.

Practice again preserved D(3,2), P/R/C(3,1), including all means, intervals and
counts. It cleared progress, feedback, selections and chat, and started with
unused q_74ad7f9ecfa8ba293a6976f4 (tangent interpretation).
The reset confirmation click preserved those beliefs; “Erase evidence and restart”
restored all four Beta(1,1), mean 50%, interval 5–95%, zero evidence.
Browser console inspection returned no warnings/errors.

Selected final runtime evidence (full log remains local at
/tmp/minds-machines-live.log):

    runtime_start pid=38703 configured_provider='bedrock' configured_model='amazon.nova-lite-v1:0' region='us-east-1'
    bedrock_converse_started
    bedrock_response_received stop_reason=tool_use
    provider_returned provider=bedrock latency_ms=15133.2
    bedrock_converse_started
    bedrock_response_received stop_reason=tool_use
    provider_returned provider=bedrock latency_ms=1800.3
    course_ingestion_ready concepts=4 questions=15 provider_calls=2 repaired_questions=0 discarded_questions=1
    POST /api/v1/courses HTTP/1.1 201 Created
    POST /api/v1/sessions HTTP/1.1 201 Created

Workshop STS succeeded before the live rehearsal. No credentials were printed.
The final generic run completes the runtime acceptance checklist, with the
source-recall limitation stated above; it does not claim to solve unrestricted
semantic validation of application MCQs.

## Commits and changed files

Implementation commit: `d7147ec971cb2c1f1909ffa164876ed14faf7a50`.
The accompanying report commit contains this audit. Both stay on the assigned
feature branch; nothing was pushed or merged. PDF fixtures are marked binary in
.gitattributes so Git does not treat PDF cross-reference whitespace as source-code
formatting. Final whitespace checks include staged content.

- `.gitattributes`
- `README.md`
- `backend/app/agents/coordinator.py`
- `backend/app/api/courses.py`
- `backend/app/api/routes.py`
- `backend/app/ingestion/passages.py`
- `backend/app/ingestion/pipeline.py`
- `backend/app/learner/bayesian.py`
- `backend/app/learner/evidence.py`
- `backend/app/learner/fake.py`
- `backend/app/policy/practice.py`
- `backend/app/storage/dynamo.py`
- `backend/app/storage/memory.py`
- `backend/app/teaching/flashcards.py`
- `backend/tests/ingestion/fixtures/calculus_derivatives_mini_lecture.pdf`
- `backend/tests/ingestion/pool_fixture.py`
- `backend/tests/ingestion/test_passages.py`
- `backend/tests/ingestion/test_pools.py`
- `backend/tests/ingestion/test_source_completion.py`
- `backend/tests/storage/test_courses.py`
- `backend/tests/storage/test_dynamo.py`
- `backend/tests/storage/test_profiles.py`
- `backend/tests/teaching/test_runtime_catalog.py`
- `contracts/api.ts`
- `contracts/fixtures/turn_response.json`
- `contracts/models.py`
- `docs/CONTRACTS.md`
- `frontend/src/App.tsx`
- `frontend/src/components/study/AnswerImpact.tsx`
- `frontend/src/components/study/BetaDistributionPlot.tsx`
- `frontend/src/components/study/EvidenceComparison.tsx`
- `frontend/src/components/study/Flashcards.tsx`
- `frontend/src/lib/courses.ts`
- `frontend/src/style.css`
- `frontend/tests/adaptive-flashcards.test.tsx`
- `frontend/tests/chatbot.test.tsx`
- `frontend/tests/courses.test.tsx`
- `frontend/tests/flashcards.test.tsx`
- `frontend/tests/posterior.test.tsx`
- `frontend/tests/study-flow.test.tsx`
- `scripts/smoke.py`
- `tests/integration/test_adaptive_pools.py`
- `tests/integration/test_chat.py`
- `tests/integration/test_course_sessions.py`
- `tests/integration/test_loop.py`
- `tests/integration/test_remediation.py`
- `tests/integration/test_uploaded_course_runtime.py`
- `docs/ADAPTIVE_POOLS_REPORT.md` (this report)
