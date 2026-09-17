# Learner-aware coaching and focus practice — final audit

Implemented on `codex/learner-aware-focus-practice` from healthy baseline `74864f2`.
Implementation commit: `170276f` (`Add trusted learner coaching and continuous focus practice`).
No main checkout, merge, main push, deployment, credentials change or delegated coding session.
The feature branch was not pushed. The local live app remains available at http://127.0.0.1:5173.

## 1. Baseline reproduced

The branch began clean at `74864f2`, matching fetched `origin/main` (0 behind / 0 ahead).
The original `make check` passed before implementation. Inspection reproduced the
10-question rich-session cap, persistent profiles and exposure ledger, authoritative
RealAssessor/BayesianLearner boundaries, course chat with counts but no complete analytics,
and the absence of a linked focus-practice flow.

## 2–3. Diagnostic budget and actual distribution

Rich initial sessions use `min(safe bank size, 4 × concept count)` submissions.
Coverage and existing adaptive retry remain; unsure/review cannot fabricate observations.
Exploratory uploads honestly retained 15 questions after individual validation failures.
The final clean upload produced 16 questions / four concepts in ONE Bedrock ingestion
call, with zero repairs or discards. It was uploaded again because the runtime was
restarted for the required clean rehearsal, not to force a desired bank size.

All final diagnostic answers were submitted through the browser and assessed by the
real runtime. No posterior was directly edited.

| Concept | Correct | Incorrect | Accepted | Posterior | Mean | 90% interval |
|---|---:|---:|---:|---|---:|---|
| Derivative as Instantaneous Rate of Change | 2 | 2 | 4 | Beta(3,3) | 50.0% | 18.9–81.1% |
| Power Rule | 4 | 0 | 4 | Beta(5,1) | 83.3% | 54.9–99.0% |
| Product Rule | 1 | 3 | 4 | Beta(2,4) | 33.3% | 7.6–65.7% |
| Chain Rule | 0 | 4 | 4 | Beta(1,5) | 16.7% | 1.0–45.1% |

Completion showed 16 submissions, 16 unique issued questions, 16 accepted observations,
zero review attempts and 16 lifetime observations. The four plot shapes visibly differed.

## 4–5. Focus ranking and interpretation

Trusted priority is `0.55(1−mean) + 0.30(interval width) + 0.15 max(0,4−evidence count)/4`.
Unseen availability, capped at three, breaks equal-score ties; stable concept ID is the
final tie-break. Recent/lifetime exposure determines availability. There is no opaque
model or LLM ranking function.

Mean below 0.5 produces `low_mastery`; interval width above 0.5 produces
`high_uncertainty`; fewer than four observations produces `limited_evidence`.
These are independent reasons. After the diagnostic, Chain Rule ranked first for low
mastery, Product Rule showed both low mastery and uncertainty, and Derivative showed
uncertainty despite a middle estimate. Thus the policy does not simply sort by mean.

## 6–7. Trusted chat contract and behavior

`CoachContext` contains session completion/kind and trusted ordered `FocusPriority`
records: concept ID/name, priority, mean, interval, evidence count, unseen availability,
and reasons. API projections are rebuilt from the current stored learner state on each
request. Provider context removes internal IDs and excludes grading keys, rubrics,
question registry and alpha/beta. The same public analytics accompany chat responses.

The browser verified chat before practice, after four answers, after diagnostic
completion, after focus, after flashcards, after Practice Again and after explicit reset.
Values and intervals reflected the current profile at every checkpoint. No chat turn
changed evidence. The server resolved “Give me more practice on my weakest concept”
to the current policy-selected concept and returned a clickable action.

A live exploratory reply tried to recommend a different first topic despite the supplied
ranking. This was fixed before the final clean run: the server now renders performance
statistics AND ordered rationale; Bedrock may supply only a checked study tip for the
trusted target. A tip containing performance/ranking/numeric claims or another concept
name is discarded. This is a conservative heuristic, not a semantic correctness proof.

**Provenance distinction:** all seven performance-related messages in the final run
used the server-authored summary after the tip filter rejected provider prose. Those
responses are explicitly `teaching_source=authored` (the existing chat UI calls them
“Local study notes”). They are not claimed as accepted AI-generated coaching prose.
The provider was genuinely called with the learner context. A separate course question
received an accepted, course-grounded Bedrock explanation of the chain rule, visibly
labeled “AI-generated response.” No fake provider was used for live proof.

## 8–10. Focus architecture, generation and exposure

`POST /api/v1/focus-practice` validates the active session/profile, uploaded course and
selected concept. It creates an explicit linked focus session with its own bounded
question IDs, budget, history and start snapshot, preserving the same profile and
posterior. The old session is retired by the existing active-session guard.

It prefers existing safe unseen items, then at most ONE bounded 12-second provider
operation for missing slots. Generic source sections supply unused source statements.
The existing source-completion resolver and ingestion validators enforce trusted answers,
source matches, positive prompts, ambiguity, duplication and leakage checks. Valid
items survive invalid neighbors. There is no subject/filename-specific production path.
If only fewer safe fresh questions exist, the set is shorter; if none survives, review
is explicitly labeled and cannot add evidence.

Exposure tracks IDs, normalized stems, content fingerprints and detectable source-fact
containment across linked sessions. New IDs or distractors cannot make seen facts fresh.
Generated questions persist in the same profile and reset only with explicit learner
reset. Issued/abandoned previews are reserved as exposed. Final browser automation
rejected repeated fresh stems; all six generated focus questions were unseen.

## 11–12. Same-posterior proof and exact live changes

The first focus set started with the diagnostic's Chain Rule **Beta(1,5)**, never Beta(1,1).
One live Bedrock generation operation returned three individually accepted questions.
The browser answered all three correctly through RealAssessor and watched the selected
Beta curve update after every accepted answer:

| Checkpoint | Posterior | Mean | 90% interval | Lifetime concept evidence |
|---|---|---:|---|---:|
| Focus start | Beta(1,5) | 16.7% | 1.0–45.1% | 4 |
| Fresh answer 1 | Beta(2,5) | 28.6% | 6.3–58.2% | 5 |
| Fresh answer 2 | Beta(3,5) | 37.5% | 12.9–65.9% | 6 |
| Fresh answer 3 | Beta(4,5) | 44.4% | 19.3–71.1% | 7 |

Focus recap: 3 submissions, 3 unique questions, 3 accepted focus observations, zero review
attempts and 19 lifetime observations. The plot overlays the actual Beta(1,5) start curve.
Interval width changed from 44.0 to 51.8 percentage points: evidence can move a boundary-heavy
posterior toward the middle and widen its interval. The UI reports this honestly.

A second Product Rule focus cycle verified repeated learning without reset. One more
bounded Bedrock operation accepted three fresh questions. Unsure preserved Beta(2,4),
a correct answer produced Beta(3,4), and a wrong answer produced Beta(3,5).
Its recap showed 3 submissions, 2 accepted focus observations and 21 lifetime observations.

## 13–16. Reranking, flashcards, Practice Again and reset

After Chain Rule focus, the ranking became Product Rule → Derivative → Chain Rule →
Power Rule. Derivative ranked above Chain Rule despite a higher mean because its
uncertainty was greater. “What should I focus on now?” showed these current values.

Flashcards opened with Product Rule first and retained all 12 cards. Reveal, “Got it,”
view switching and return to chat left beliefs unchanged. Chat → focus → flashcards →
chat → another focus cycle worked without refreshing.

Practice Again preserved Derivative Beta(3,3), Power Beta(5,1), Product Beta(3,5), Chain
Beta(4,5): 21 total observations. It labeled the reused next question as review. A correct
review answer kept Product Beta(3,5), with observations 6 → 6 and an explicit no-evidence
message. No evidence double-counting occurred.

Only “Reset learner profile” followed by “Erase evidence and restart” restored every
concept to Beta(1,1), mean 50%, interval 5–95%, zero evidence. Old chat disappeared;
post-reset chat and ranking used priors and `high_uncertainty` / `limited_evidence`,
with no stale low-mastery reason.

## 17. Defects addressed

- The 10-question cap under-supported four-concept diagnostics: raised the bounded target.
- Chat lacked trusted mastery, intervals and focus rationale: added a current read-only projection.
- No linked focus workflow or same-posterior visualization existed: added both.
- Generated candidate slots could inherit prohibited negative source wording: reject before calling.
- Generated focus questions were initially omitted when resolving chat's current topic: load them first,
  with a regression that inspects provider context.
- Provider prose could contradict trusted ranking: moved policy explanation into server text and
  restricted optional provider tips; regression rejects conflicting recommendations/invented percentages.
- Lifetime and session counts could be confused: added explicit counts and recap labels.
- New long frontend lifecycle coverage exceeded a five-second test limit under suite load: set 15 seconds
  for that test; the complete suite then passed. Updated exact contract/fixture assertions intentionally.

## 18. Files changed

Implementation files, tests and documentation relative to `74864f2`:

- `README.md`
- `backend/app/api/routes.py`
- `backend/app/policy/focus.py`
- `backend/app/policy/practice.py`
- `backend/app/storage/dynamo.py`
- `backend/app/storage/memory.py`
- `backend/app/teaching/chat.py`
- `backend/app/teaching/focus_questions.py`
- `backend/app/teaching/remediation.py`
- `backend/tests/storage/test_dynamo.py`
- `backend/tests/storage/test_profiles.py`
- `contracts/api.ts`
- `contracts/fixtures/turn_response.json`
- `contracts/models.py`
- `docs/CONTRACTS.md`
- `docs/LEARNER_AWARE_FOCUS.md`
- `docs/LEARNER_AWARE_FOCUS_REPORT.md` (this audit)
- `frontend/src/App.tsx`
- `frontend/src/components/study/FocusRanking.tsx`
- `frontend/src/components/study/StudyChatbot.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/style.css`
- `frontend/tests/focus-practice.test.tsx`
- `tests/integration/test_adaptive_pools.py`
- `tests/integration/test_course_sessions.py`
- `tests/integration/test_focus_practice.py`

## 19–22. Commits and automated verification

Implementation: `170276f`. This audit is committed separately as
`Document complete live learner coaching and focus audit`; its hash is in the final handoff.

Final `make check` passed:

| Suite | Passed |
|---|---:|
| Integration, including 11 new focus/coaching/generation cases | 101 |
| Agents / assessor / provider / coordinator | 41 |
| Teaching / remediation / runtime catalog | 136 |
| Ingestion / pools / source validation | 95 |
| Auth | 10 |
| Learner | 21 |
| Policy | 27 |
| Storage | 18 |
| Backend total | **449** |
| Frontend: study flow, chat, focus, flashcards, posterior and existing regressions | **87** |

Typecheck and production Vite build passed. Existing nonfatal dependency “use client” /
bundle-size warnings and jsdom `scrollTo` notices remain. There were no failed tests.
Focused policy, evidence, focus lifecycle, chat analytics, bounded/partial generation,
reset, source-exposure and storage cases ran before the full suite as well.

`make smoke`: PASS — actual HTTP loop, all interventions, fresh questions, posterior values,
reset and preference isolation. `git diff --check`: PASS.
Logs: `/tmp/minds-focus-final-check.log`, `/tmp/minds-focus-final-smoke.log`.

## 23–24. Final browser and real AWS evidence

After the final source changes and passing checks, the backend and frontend were stopped
and restarted with clean in-memory state and a fresh browser tab. All stages above were
performed through the browser with real requests, the supplied Calculus PDF and real
Bedrock. No browser refresh was needed during the learning loop. Final browser console
inspection returned no warnings or errors. Screenshots visually confirmed distinct
completion distributions and the Chain Rule before/after overlay.

`aws sts get-caller-identity --profile workshop` succeeded before implementation and
was rechecked at handoff (workshop participant role). No credentials were printed or stored.
Runtime configuration and sanitized proof from `/tmp/minds-machines-live.log`:

```text
runtime_start pid=94419 configured_provider='bedrock'
  configured_model='amazon.nova-lite-v1:0' region='us-east-1' timeout_seconds='12'
course_ingestion_ready concepts=4 questions=16 provider_calls=1
  repaired_questions=0 discarded_questions=0
focus_generation accepted=3 requested=3
focus_generation accepted=3 requested=3
```

Final clean-run totals:

- `bedrock_converse_started`: **53**
- `bedrock_response_received`: **53**
- `provider_returned provider=bedrock`: **53**
- Provider failures: **0**
- Successful answer turns: **23** (16 diagnostic + 3 Chain focus + 3 Product focus + 1 review)
- HTTP 4xx/5xx responses: **0**
- Performance chat summaries: **7 server-authored**, following real provider calls and rejected tips
- Accepted course-chat Bedrock response: **1**

The final UI is left after explicit reset, showing priors and the reset-aware coach summary.

## 25. Remaining limits and review notes

- Exact-source recall is not validated application-level knowledge. Literal validators and
  conservative equivalence checks cannot prove arbitrary semantic novelty or correctness.
- The priority formula is an explainable demo heuristic; four observations remain limited evidence.
- The conservative coach-tip filter rejected all seven performance tips in this live run. Trusted
  explanations still worked, but this can reduce conversational variety. The UI's existing authored
  label is “Local study notes”; source provenance is recorded explicitly above.
- Fresh source material is finite. Replenishment can legitimately return fewer items or review only.
- Profiles persist across linked sessions within the running memory backend. Restart/reload recovery
  and distributed locking retain baseline limitations. Dynamo serialization was tested locally, not
  against a live DynamoDB table; the requested live run intentionally left its table setting empty.
- Shared contracts and cross-owner changes need human review before merge. `origin/main` was fetched
  and compared; GitHub PR overlap/mergeability was not verified because `gh` is unavailable. No merge
  is requested or claimed, and no main changes were made.

## 26. Final Git state

After committing this audit, expected and checked `git status --short --branch`:

```text
## codex/learner-aware-focus-practice
```

No staged, unstaged or untracked task files remain. Main is untouched and the feature
branch is local and reviewable.
