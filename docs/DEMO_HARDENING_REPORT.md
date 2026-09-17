# Live demo hardening report

Final verification: 2026-09-17 (America/Denver). Branch: `codex/chatbot_repair_full_auto_demo`. Base: `dde69c6` (`Stabilize live course ingestion and adaptive demo`). The worktree was initially clean and HEAD equaled the requested baseline. No branch switch, main modification, merge, deployment or push was performed.

## Root cause and fixes

The chatbot was an unconnected prototype: the composer stored a local draft, Send was permanently disabled, and there was no client call, backend chat route, chat service or conversation storage. Practice feedback could be displayed, but student messages could not reach Bedrock.

Added an additive typed `/api/v1/chat` request/response, server-resolved course context, bounded Bedrock conversation service, session-owned history, backward-compatible Dynamo serialization, and a working frontend Send flow. The UI shows loading/provenance, keeps failed drafts for retry, validates returned session identity, and resets conversation on session/course change. Live failures surface explicitly; local mode is labeled local notes. See [CHAT.md](CHAT.md) for the contract and limits.

Additional issues found and fixed:

- Overlapping session operations could overwrite a previously loaded state snapshot. A per-session guard now rejects concurrent quiz/chat writes, releases on failure, and quiz writes preserve chat history. The UI blocks duplicate sends and conflicting submissions/reset.
- Advancing to a different concept left the evidence inspector on the previous concept; review also labeled the next topic as practicing. Next/revisit now select the matching concept and review derives its focus from the assessed question. Completion no longer labels a concept as being practiced.
- New chat replies could be hidden below the conversation scroll area. Replies now scroll within the conversation, have a Latest response control, and are interleaved chronologically with quiz explanations. Chat activity also has accurate counts/loading text.
- The missing favicon caused a browser console 404. Added the existing brand motif as an SVG favicon.

No changes were needed to grading, Bayesian calculations, quantitative policy, ingestion validators, targeted-question validation or flashcard evidence rules. Answer keys, course/question identity and remediation records remain server-owned.

## Automated verification

`make check`: PASS — 421 backend tests and 80 frontend tests; TypeScript and production build passed. This includes chatbot, uploads, learner, policy, Tutor, remediation, flashcards, storage, course isolation and frontend transitions. `make smoke`: PASS — real local HTTP loop, all three interventions, posterior values, fresh questions, reset and preference isolation. `git diff --check`: PASS.

New coverage tests trusted chat context/history, post-answer observations, reset isolation, missing courses, forged fields, invalid/oversized messages, provider/validation failure, explicit prompt/control disclosure, bounded history, concurrency, Dynamo legacy/round-trip behavior, duplicate sends, retry, navigation, reset, returned-session mismatch and concept-inspector transitions.

Build notes: existing third-party use-client/chunk-size warnings and jsdom scrollTo notices remain non-failing. The final live browser reported no console errors or uncaught exceptions.

## Final clean live browser run

After all application fixes and automated checks, restarted FastAPI/Vite from the repository root with the requested environment: `MODEL_PROVIDER=bedrock`, `AWS_PROFILE=workshop`, `AWS_REGION=us-east-1`, `BEDROCK_MODEL_ID=amazon.nova-lite-v1:0`, 12-second interactive/60-second ingestion timeout, and empty DynamoDB table. Used headless Chrome with the actual React UI and no intercepted or mocked provider/API responses. Screenshots were visually inspected.

Only `calculus_derivatives_mini_lecture.pdf` was uploaded. `POST /courses` returned 201; initial and reset `POST /sessions` returned 201. Four concepts were returned: instantaneous rate of change, Power Rule, Product Rule, Chain Rule. The final bank had seven questions and four grounded flashcards.

Ingestion diagnostics: initial generation plus one bounded repair; the second Chain Rule slot remained ambiguous and was safely discarded. `concepts=4 questions=7 provider_calls=2 repaired_questions=0 discarded_questions=1`. Every concept retained a usable question. No validation was weakened. The earlier exploratory live run produced eight valid questions without repair; final evidence below is from the fresh seven-question run.

Initial state for every concept: mean 0.5, 90% interval [0.05, 0.95], evidence count 0. Initial question, selected concept, estimates and counters rendered correctly.

### Adaptive pass: every available question

For each row, the browser checked the exact prompt/concept, empty prior selection, disabled empty/pending submit, selected radio, request/response session, four-stage trace, expected grading, concept-isolated evidence change, displayed estimate/interval/count, progress, fresh next ID, and completion. No unintended repetitions or skips occurred.

| # | Question ID | Prompt | Answer/outcome | Posterior mean | 90% interval | Evidence | Next activity |
|---|---|---|---|---|---|---|---|
| 1 | `q_85db4e88004aa14b48622503` | 1. Derivative as Instantaneous Rate of Change: What does a derivative measure in terms of a quantity's change? | b / incorrect | 0.333333 | [0.0253, 0.7764] | 1 | diagnostic_probe |
| 2 | `remediation-466aea667dc0442abdb941bb91e3028c` | What is the instantaneous rate of change of y with respect to x at a point on the graph of y = f(x)? | a / correct | 0.500000 | [0.1354, 0.8646] | 2 | Next concept |
| 3 | `q_d89e3aa09c282b21ac2d7b0a` | 2. Power Rule: What does the power rule state for differentiating a function of the form f(x) = x^n? | unsure / unclear | 0.500000 | [0.05, 0.95] | 0 | diagnostic_probe |
| 4 | `q_dff13134dee9a9e96e159156` | 2. Power Rule: What happens to constant coefficients when applying the power rule? | b / correct | 0.666667 | [0.2236, 0.9747] | 1 | Next concept |
| 5 | `q_db3ac34ad3d8190c0e923d1f` | 3. Product Rule: What is the product rule for differentiating a function h(x) = u(x)v(x)? | a / correct | 0.666667 | [0.2236, 0.9747] | 1 | diagnostic_probe |
| 6 | `q_d9b6b9d3019f9832e7acc963` | 3. Product Rule: How is the product rule applied when differentiating a product of two functions? | b / correct | 0.750000 | [0.3684, 0.983] | 2 | Next concept |
| 7 | `q_d915aa4363747712bf023361` | 4. Chain Rule: What does the chain rule state about differentiating a composition of functions? | a / correct | 0.666667 | [0.2236, 0.9747] | 1 | Complete |

The first incorrect answer was graded by RealAssessor from the trusted key. BayesianLearner moved instantaneous-rate mastery from 0.5 to 1/3 and evidence from 0 to 1. AdaptivePolicy chose a diagnostic probe (selection priority 0.7215), Tutor returned accepted Bedrock teaching, and an accepted generated remediation question replaced the remaining fresh slot for the same weak concept. Its correct response was graded using the server-held generated key, moving the posterior to 0.5 with two observations and interval [0.1354, 0.8646]. The unresolved focus then cleared.

The unsure Power Rule response added no evidence and left its complete estimate unchanged. Subsequent correct answers updated only their own concepts. Concept transitions and completion used authored messages as designed; interior teaching used accepted Bedrock output.

### Original bank coverage after reset

The adaptive pass intentionally replaced one original slot. A second all-correct browser pass in the fresh session traversed all seven original bank questions, covering that replaced question too. Answer selection was preserved through quiz → chatbot → quiz before each submission.

| # | Original question ID | Prompt | Result |
|---|---|---|---|
| 1 | `q_85db4e88004aa14b48622503` | 1. Derivative as Instantaneous Rate of Change: What does a derivative measure in terms of a quantity's change? | correct / HTTP 200 |
| 2 | `q_ff57449b61b5723a42d50408` | 1. Derivative as Instantaneous Rate of Change: What is the relationship between f'(x) and the slope of the tangent line at a point on the graph of y = f(x)? | correct / HTTP 200 |
| 3 | `q_d89e3aa09c282b21ac2d7b0a` | 2. Power Rule: What does the power rule state for differentiating a function of the form f(x) = x^n? | correct / HTTP 200 |
| 4 | `q_dff13134dee9a9e96e159156` | 2. Power Rule: What happens to constant coefficients when applying the power rule? | correct / HTTP 200 |
| 5 | `q_db3ac34ad3d8190c0e923d1f` | 3. Product Rule: What is the product rule for differentiating a function h(x) = u(x)v(x)? | correct / HTTP 200 |
| 6 | `q_d9b6b9d3019f9832e7acc963` | 3. Product Rule: How is the product rule applied when differentiating a product of two functions? | correct / HTTP 200 |
| 7 | `q_d915aa4363747712bf023361` | 4. Chain Rule: What does the chain rule state about differentiating a composition of functions? | correct / HTTP 200 |

Both passes reached completion with correct progress (7/7); the adaptive pass recorded six accepted observations and the all-correct pass seven. There were fourteen successful turn requests total.

### Chat, flashcards, navigation and reset

All six live chat requests returned HTTP 200 with `teaching_source=bedrock`: the three requested conceptual prompts, a follow-up on the weak concept after the Bayesian update, a rules summary after completion, and the instantaneous-rate prompt again after reset. Responses described derivatives/tangent slopes, the Power Rule, and product-versus-composition differentiation; no Intro AI content appeared. The conversation survived view changes and remained usable after learning/completion.

After the wrong answer, the weak concept was first in the returned flashcard ordering and rendered first in the UI. Reveal, Review again, Got it, next, previous, and quiz → flashcards → chatbot → quiz were exercised. Two self-ratings were recorded without any API request or Bayesian change. The existing automated flashcard suite also verifies deck completion, topic filtering, reordered cards and retained ratings.

Reset retained the same uploaded course, restored every prior, returned the original first question, cleared selections/feedback/remediation/transcript, and reset flashcard review progress to zero. A fresh Bedrock chat succeeded. The original-bank pass then completed in that new session. The presenter never needed a browser refresh to recover.

Final browser summary: `questions=7 originalBankQuestions=7 chats=6 errors=[] badResponses=[]`. Startup, all course/session/chat/turn requests, and the favicon were free of failed HTTP responses in the final run.

## Real AWS evidence

`aws sts get-caller-identity --profile workshop` succeeded before implementation. Runtime startup logged `configured_provider=bedrock`, `region=us-east-1`, and `configured_model=amazon.nova-lite-v1:0`. The final runtime recorded 28 each of `bedrock_converse_started`, `bedrock_response_received`, and `provider_returned`, six accepted `chat_result` lines, and `targeted_question_result reason=accepted`. No provider failure occurred in the final run.

Local evidence (not committed, synthetic demo data): `/tmp/minds-hardening-final/` contains response JSON, question audits and screenshots; `/tmp/minds-hardening-final.log` contains the browser audit; `/tmp/minds-machines-live.log` contains runtime/provider diagnostics; `/tmp/minds-hardening-check2.log` and `/tmp/minds-hardening-smoke.log` contain check/smoke output. The temporary browser harness is `/tmp/minds-hardening-browser.cjs`.

## Remaining limits and preflight

- Bedrock output remains stochastic: question count may vary, and safe rejection/one repair can discard a slot. Credentials, model access, network and availability remain external demo dependencies.
- Chat is grounded by public notes and instruction/output checks, not a general semantic correctness proof. Concept explanations can overlap public study notes; private grading keys are never sent to the model.
- The supported demo is one process with in-memory state. Restart/reload recovery, distributed locks, production session authorization and Cognito/Dynamo deployment were not part of this verification. Chat history retains the last twelve successful exchanges.
- Seven-check preflight: assigned branch verified; fetched origin/main comparison was 0 behind/0 ahead before edits; all paths authorized by this task; additive shared-contract change explicitly flagged/documented; no base divergence/conflict; check and smoke passed. GitHub showed no open PRs during the overlap check. Teammate review remains pending; no merge is authorized.

## Changed files

- `README.md`
- `backend/app/api/routes.py`
- `backend/app/storage/dynamo.py`
- `backend/app/storage/memory.py`
- `backend/app/teaching/chat.py`
- `backend/tests/storage/test_dynamo.py`
- `contracts/api.ts`
- `contracts/models.py`
- `docs/CHAT.md`
- `docs/CONTRACTS.md`
- `docs/DEMO_HARDENING_REPORT.md`
- `frontend/index.html`
- `frontend/public/favicon.svg`
- `frontend/src/App.tsx`
- `frontend/src/components/study/StudyChatbot.tsx`
- `frontend/src/lib/api.ts`
- `frontend/tests/chatbot.test.tsx`
- `frontend/tests/courses.test.tsx`
- `frontend/tests/study-flow.test.tsx`
- `tests/integration/test_chat.py`
