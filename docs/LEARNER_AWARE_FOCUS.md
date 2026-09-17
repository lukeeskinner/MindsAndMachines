# Learner-aware coaching and focus practice

Authorized scope: `codex/learner-aware-focus-practice`, baseline `74864f2`.
This feature changes the shared Python/TypeScript API and golden response together.
It leaves RealAssessor grading, BayesianLearner updates and AdaptivePolicy intervention
selection authoritative. Chat and flashcards remain non-evidence.

## Lifecycle and contracts

Rich-source diagnostic sessions have a maximum `min(bank size, 4 × concept count)`
submission budget. Selection prefers lifetime-unseen items, covers concepts and
allows the existing immediate same-concept retry after an incorrect answer.
Normal answers can yield four accepted observations per concept. Unsure responses
consume an item but add no evidence; completion never waits indefinitely for evidence.
Smaller safe banks complete with fewer observations. No diagnostic regeneration is required.

Session and turn responses include read-only `analytics`: session completion, explicit
`diagnostic | focus` kind and an ordered `focus_ranking`. Each row includes trusted
concept identity/name, priority, mean, 90% interval, evidence count, unseen availability
and reasons. Chat responses also carry these analytics and an optional server-resolved
`practice_concept_id`. The frontend renders this order without calculating priority.

`POST /api/v1/focus-practice {session_id, concept_id}` validates the active profile,
course and concept, then creates a linked `focus` session with up to three questions.
It retires the previous session through the existing active-session guard. The same
profile, beliefs and exposure history continue. The new session has its own history,
budget, start snapshot and focus concept/question IDs. Starting focus from an unfinished
session abandons its current question, which remains exposed and cannot add evidence later.
A new session starts a new conversation; navigation within a session retains chat.
Practice Again also preserves beliefs; only explicit learner reset clears beliefs,
exposure and the profile's generated-item registry.

Counts distinguish current-session submissions, unique issued IDs, accepted observations,
review attempts, focus observations and lifetime profile evidence. Previewed questions
are exposed even if abandoned. Session-start comparisons never use a fresh prior for focus.

## Trusted priority and coaching

Priority = `0.55 × (1 − mean) + 0.30 × interval width + 0.15 × max(0, 4 − evidence count)/4`.
Ties prefer available unseen questions (capped at three), then stable concept ID.
`low_mastery` means mean below 0.5; `high_uncertainty` means interval width above 0.5;
`limited_evidence` means fewer than four observations. These reasons can coexist.
The score is a simple demo heuristic, not a validated clinical or educational diagnosis.
Flashcards reuse the same score, with the existing recent remediation focus first.

Every chat request projects CURRENT server estimates and ranking, completion and session
kind, alongside course notes and bounded conversation history. Keys, rubrics, private
question records, alpha/beta and internal IDs are excluded from the provider projection.
For performance/practice questions, the server renders the ordered rationale and exact
statistics. Bedrock supplies only a grounded study tip for the server-selected concept.
Tips containing numerical, performance, ranking or scheduling claims, or names
of other concepts, are discarded in favor of an explicitly authored trusted
summary. This conservative separation was added after a live model reply tried to
recommend a different first concept despite the trusted order. Bedrock failures retain the existing retry/error UI.

Practice actions resolve explicit concept names or a request for the highest-priority
area in trusted code. They never execute from model output. The student clicks an action;
the backend then validates the transition again. Chat itself cannot mutate mastery.

## Freshness and generation

Focus first uses unseen existing questions, including previously generated unissued items.
When fewer than three remain, it attempts at most ONE 12-second generation call for the
missing slots. Generic source-section expansion finds unused exact source statements;
there is no subject, filename or demo-answer branch. No eligible source statements means
no call. The existing source-completion resolver and ingestion validator check each
candidate independently: server-bound answer echo, exact source match, positive stem,
no answer leakage, unique choices and no source-supported alternative. Valid candidates
survive neighboring failures. There is no repair/retry loop for focus.

Question IDs are minted on the server. Exact IDs, normalized stems, content fingerprints
and detectable source-statement containment protect exposure across linked sessions.
Changing an ID or distractors does not make an exposed source fact fresh. The entire
current bank and generated registry are considered during replenishment. A smaller safe
fresh set is used without review padding. If none survives, the UI explicitly offers
review-only items and those answers cannot change the posterior.

These are literal source-recall questions. Validators do not prove arbitrary semantic
non-equivalence or application-level understanding. Source expansion is deliberately
conservative and may exhaust a small document. Existing anonymous memory-profile and
single-process locking limitations remain; no account recovery or distributed locking
is introduced. Dynamo serialization supports the added fields with legacy defaults.

## Visual behavior and tests

Completion and chat show the trusted priority list with focus buttons. Focus practice
keeps the selected concept's Beta plot visible before and after each answer, overlaying
its actual session-start curve. Mean, interval width and added evidence summarize change.
Existing recap plots, flashcards, materials and navigation remain in place.

Regression coverage is in `tests/integration/test_focus_practice.py`,
`frontend/tests/focus-practice.test.tsx`, the updated adaptive-pool tests and storage
round-trip tests. `make check` includes the existing assessor, learner, policy, chat,
ingestion, remediation, flashcard, storage, frontend and posterior suites. Run
`make smoke` and `git diff --check` too. Live rehearsal results are recorded separately.
