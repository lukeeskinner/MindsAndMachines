# Focus action hardening and live verification

Branch: `codex/focus-practice-action-fix`. Parent checkpoint: `5037ed4` on
`codex/learner-aware-focus-practice`; healthy main: `74864f2`.
The current user request authorizes this focused follow-up across the frontend,
integration tests and this report. No branch switch, delegated implementation,
main modification, push, merge, deployment or credential change occurred.

## Diagnosis: confirmed defect versus historical uncertainty

The original intermittent failure was **not reproduced in the fresh live browser**.
Before edits, both the initial and completed-diagnostic sequences successfully sent
`How did I do, and what should I focus on next?` followed by
`Give me more practice on my weakest concept.` FastAPI logged HTTP 200 for both;
the browser displayed the server-resolved practice action without console errors.
That exploratory diagnostic included Power Rule Beta(2,3), 40%, three observations.

The exact path is quick-action button → `setDraft` → Send → `post('chat')` → fetch
→ `/chat` → server `requested_concept` over trusted analytics → response action
→ `newSession(false, conceptId)` → `post('focus-practice')` → validated linked session.
There is no frontend intention parser. The quick action only fills the composer.

A concrete pre-HTTP compatibility defect was reproduced in a controlled frontend
regression: remove `AbortSignal.timeout`, click the weakest-concept suggestion,
then Send. The original client throws while evaluating fetch options, before fetch
is called, and maps that TypeError to the generic “learning service is unavailable”
message. The test failed before the fix and passes afterward.

**This is not proof of the historical incident's cause.** In particular, the user's
preceding successful chat used the same helper, so a permanently missing timeout
method alone would not explain that sequence. The original failing browser's
console/network capture is unavailable. A clarification about that browser was
requested during work; no reply was available when this report was written.
Do not describe the historical root cause as established.

## Changes and trusted action contract

- Shared `withRequestTimeout` uses AbortController plus a cleared timer, retaining
  the 20-second interactive and 120-second upload deadlines through body parsing.
  It removes the unconditional static timeout dependency from both HTTP clients.
- Request preparation, transport, timeout, HTTP and invalid-response failures now
  have distinct handling. Console diagnostics contain only path and a fixed reason;
  no draft text, answers, session IDs, credentials or raw exceptions are logged.
  Invalid chat payloads have their own retry message; failed drafts remain intact.
- The existing structured recommendation CTA is made explicit:
  **Start [trusted concept name] focus set**. Copy promises *up to* three fresh
  questions and explains shorter availability and labeled review. Other concept
  buttons remain available. This improves an existing structured action; it does
  not introduce a new endpoint or rely on interpreting display text.
- Public contracts are unchanged. The UI renders `analytics.focus_ranking` in the
  server's order, binding `concept_id` directly. Natural-language chat returns
  `practice_concept_id` from backend policy/name resolution. Both action paths send
  `{session_id, concept_id}` to `/api/v1/focus-practice`. The direct recommendation
  action needs no chat request or chat-model success.

The existing focus architecture remains intact: validate active session/course and
concept → reuse the same persisted profile → select unseen questions → at most one
bounded generation call for missing slots → validate trusted source answers →
short linked focus session. RealAssessor grades, evidence eligibility controls
updates, BayesianLearner updates the existing posterior, and server estimates and
ranking refresh the plots. Chat and flashcards never grade or add evidence.

## Final live browser proof (no mocks)

After client changes, a new upload and learner profile were used in the Codex
in-app browser. The source was the repository's
`backend/tests/ingestion/fixtures/calculus_derivatives_mini_lecture.pdf`.
The run used workshop credentials, real Bedrock Nova Lite in `us-east-1`, and the
requested `make dev` environment with in-memory storage. STS identity verification
succeeded. No client source changes/reloads occurred during this final learning loop.

Ingestion retained 15 safe questions and 12 cards after one repair attempt and one
rejected question. Every diagnostic answer went through the real browser/API loop.
The completed diagnostic had these server-owned plots:

| Concept | Alpha | Beta | Mean | 90% interval | Evidence |
|---|---:|---:|---:|---|---:|
| Derivative | 2 | 4 | 33.3% | 7.6–65.7% | 4 |
| Power Rule | 2 | 4 | 33.3% | 7.6–65.7% | 4 |
| Product Rule | 3 | 2 | 60.0% | 24.9–90.2% | 3 |
| Chain Rule | 3 | 3 | 50.0% | 18.9–81.1% | 4 |

Both exact chat prompts succeeded; the weakest-concept quick-action/button + Send
was also repeated successfully. Trusted ranking was Derivative → Power → Chain →
Product. The student clicked the direct Derivative focus CTA.

Only **two** safe fresh Derivative items survived the bounded generation call.
The UI explicitly announced two questions; no repeats or review padding were used.
Both had source statements distinct from the diagnostic. The focus plot preserved
its session-start curve and changed immediately after each accepted answer:

| Checkpoint | Alpha | Beta | Mean | 90% interval | Evidence |
|---|---:|---:|---:|---|---:|
| Before focus | 2 | 4 | 33.3% | 7.6–65.7% | 4 |
| Focus starts | 2 | 4 | 33.3% | 7.6–65.7% | 4 |
| Correct fresh answer | 3 | 4 | 42.9% | 15.3–72.9% | 5 |
| Wrong fresh answer / completion | 3 | 5 | 37.5% | 12.9–65.9% | 6 |

Percentages/intervals are the actual UI's rounded server values. Alpha/beta and
counts are exact. No Beta(1,1) appeared during the transition. The integration
regression additionally checks identical profile IDs and persisted state after
each answer and each rejected duplicate.

“What should I focus on now?” returned **Power → Derivative → Chain → Product**,
with Power at 33.3%/four observations and Derivative at 37.5%/six observations.
Starting that newly recommended Power focus preserved Beta(2,4). Only **one** safe
fresh item survived; the UI announced that limit. Answering unsure preserved
alpha=2, beta=4, mean=33.3%, interval=7.6–65.7%, evidence=4. There were 17 lifetime
accepted observations after 18 submissions across these sessions.

The final run therefore demonstrates honest short sets (two and one), not a live
three-question set. Three fresh questions in one set, partial/exhausted generation,
duplicate rejection and no-review-evidence behavior are covered by integration tests.

A subsequent performance chat used the current ranking and values. A separate
Product Rule explanation returned accepted Bedrock prose, visibly labeled
“AI-generated response.” This proves real conversational inference, not a semantic
correctness guarantee for every generated explanation. Performance replies used
server-authored analytics after provider-tip rejection, correctly labeled local
study notes; these are not claimed as accepted AI-generated coaching prose.

Flashcards retained all 12 cards with **Power Rule first**, matching the new trusted
priority. Reveal and “Got it” worked without adding evidence. Practice Again
preserved Derivative Beta(3,5), Power Beta(2,4), Product Beta(3,2), Chain Beta(3,3).
It labeled the reused Power item as review; a correct review answer left Beta(2,4)
and four observations unchanged.

Only **Reset learner profile → Erase evidence and restart** restored all four
concepts to Beta(1,1), mean 50%, interval 5–95%, zero observations. The live tab is
left at that verified reset state. Final console inspection returned no warnings
or errors. Screenshots and DOM observations confirmed plot continuity and counts.

Final-run log segment (after line 209 in `/tmp/minds-machines-live.log`):
44 Bedrock starts and 44 successful returns; zero provider failures;
19 successful answer POSTs (15 diagnostic, two Derivative focus, one unsure Power
focus, one review); six successful chat POSTs; two focus POSTs returning HTTP 201.
Generation logged `accepted=2 requested=3` and `accepted=1 requested=3`.
No final-run HTTP 4xx/5xx response occurred. Every focus action reached FastAPI.

## Verification and handoff

- Controlled pre-fix compatibility regression: failed as expected; post-fix passed.
- Targeted frontend API/chat/focus tests: 9 passed.
- Targeted focus/adaptive-pool/chat integration tests: 24 passed.
- `make check`: PASS — 449 backend tests, 93 frontend tests, TypeScript and Vite build.
  Includes 21 learner and 27 policy tests, chat isolation, ingestion safety,
  concurrency guards, flashcards, persistence and reset regressions.
- The first full check hit the existing chat lifecycle test's five-second timeout
  under suite load. Its allowance is now 15 seconds, matching the focus lifecycle
  test; no assertions were removed. The complete check then passed.
- `make smoke`: PASS — real HTTP core loop, interventions, freshness, posterior,
  reset and presentation-preference isolation.
- `git diff --check`: PASS.
- Existing nonfatal bundle-size and jsdom scrollTo warnings remain.

Logs: `/tmp/focus-action-before.log`, `/tmp/focus-action-targeted-ui.log`,
`/tmp/focus-action-targeted-backend.log`, `/tmp/focus-action-check.log`,
`/tmp/focus-action-smoke.log`, `/tmp/minds-machines-live.log`.

Seven-check preflight: assigned branch confirmed; origin fetched (zero behind,
two inherited commits ahead before this task); task paths reviewed; no public
contract changes; no conflict markers; check and smoke passed. Remote PR overlap
and GitHub mergeability are unverified because `gh` is unavailable. No merge is
requested. Memory-profile recovery/distributed-locking limits remain unchanged.
The report and changes are committed locally; the final response supplies the
commit SHA and verified clean status.

Files changed in this follow-up:

- `frontend/src/lib/requestTimeout.ts`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/courses.ts`
- `frontend/src/components/study/StudyChatbot.tsx`
- `frontend/src/components/study/FocusRanking.tsx`
- `frontend/tests/api.test.ts`
- `frontend/tests/chatbot.test.tsx`
- `frontend/tests/focus-practice.test.tsx`
- `tests/integration/test_focus_practice.py`
- `docs/FOCUS_ACTION_FIX_REPORT.md`
