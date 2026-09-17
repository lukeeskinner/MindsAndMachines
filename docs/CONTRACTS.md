# Minimum replaceable contracts

Status: G1 types and interfaces are implemented in `contracts/models.py`, `contracts/interfaces.py` and `contracts/api.ts`, with one example payload in `contracts/fixtures/turn_response.json`. No generated-client infrastructure was added. SWE1 owns the shared shapes and examples; the four module owners review changes. The goal is to replace each fake without changing its callers.

## Keep representation small

G2 Tutor runtime addition: `TeachingResult` and the public `tutor` object now carry
`teaching_source: authored | bedrock | authored_fallback` (default `authored` for
existing local implementations). `bedrock` means generated text passed Tutor
validation; `authored_fallback` means reviewed catalog prose was used instead,
including unclear assessment, unsupported provider, provider error/timeout or
validation failure. `fallback` remains the existing boolean. Completion is
`authored` with `fallback=false`, even when Bedrock is configured.

The existing top-level `mode` and `provider` describe the **returned teaching**:
`live/bedrock` only for accepted generation; otherwise `dummy/fake`. They do not
describe the whole pipeline or record an attempted provider. Assessment uses
RealAssessor with authoritative answer-key grading and optional Bedrock diagnosis;
these teaching labels do not describe assessment provenance.
The UI uses `tutor.teaching_source`, never prose or server
configuration, to label Authored teaching, AI-generated teaching or Reviewed
fallback. Raw model IDs are not added to learner-facing data.

The four callable signatures are unchanged. Coordinator snapshots policy choices
before Teaching, passes defensive copies, and rejects an unknown trusted next
question or a mismatching TeachingResult with a controlled integration error.
These errors return HTTP 500 with a generic configuration message before session
state/history are saved. Ordinary Tutor provider failures return HTTP 200 with
reviewed fallback and the trusted Decision/next question; the turn is not retried.

Use simple Python dataclasses or Pydantic models in `contracts/`, one shared example payload, and a small TypeScript type file there if needed. A handwritten Python/TypeScript pair is acceptable at this scale; SWE1 keeps it aligned with the example and the loop check. Type/schema/client generation is optional only when nearly free. FastAPI's built-in OpenAPI output is fine; no extra generation pipeline is required.

Use snake_case JSON keys, stable catalog IDs and finite numbers. The API validates the handful of expected fields. No request/attempt IDs, state versions, catalog/model version envelopes, event log or migration framework in G1. Keep rubrics and answer keys server-side. The following tables describe the G1 records implemented on the review branch.

## Shared records

| Record | Minimum fields |
| --- | --- |
| Question (server) | `question_id`, `concept_id`, `prompt`, `choices: list[{id,text}]`, `answer_key`, `rubric: string` |
| PublicQuestion | Question ID, concept ID, prompt and choices only |
| Assessment | `outcome` (correct/incorrect/unclear), `concept_id`, `score` (0, 1 or null), `misconception_id` (string or null), `feedback: string` |
| ConceptEstimate | `concept_id`, `mean`, `interval90: {lower,upper}`, `evidence_count` |
| LearnerState | `skills: map[concept_id, {alpha,beta,evidence_count}]` |
| LearnerUpdate | `state: LearnerState`, `concepts: list[ConceptEstimate]`, `evidence_applied: bool` |
| LearnerPresentationPreferences | `plain_language: bool`, `step_by_step: bool`, `concise: bool`; each defaults to false |
| Candidate | `candidate_id`, `concept_id`, `kind`, `content_id`, `next_question_id` (string or null) |
| Decision | Candidate fields plus `reason: string` |
| TeachingResult | `text`, `next_question_id` (string or null), `fallback: bool`, `teaching_source` |
| HistoryEntry | `question_id`, `evidence_applied: bool`, `candidate_id` (string or null) |

`kind` is `diagnostic_probe`, `worked_example` or `socratic_hint`. G1 needs only a worked example and a canned probe/completion. The curriculum hierarchy, sources, prerequisites and richer rubrics remain content metadata for G2; do not create a content database or elaborate catalog schema during G1.

Questions have one primary concept; secondary tags must not produce extra evidence. `score=null` means no update. History gives the later real learner enough context to skip an already-scored question without implementing HTTP idempotency. G1 uses two different questions and sequential submissions. The real model's unaided-evidence rules remain in ARCHITECTURE.md; hint inputs can be added through a reviewed extension when the feature is built.

Means and interval endpoints are in [0,1]; lower ≤ upper; evidence counts are nonnegative. G1 returns canned values. The future Beta implementation computes them. The frontend displays these fields and never computes mastery independently.

## Four independently replaceable seams

| Boundary | Callable | Responsibility |
| --- | --- | --- |
| Assessment/Diagnosis — SWE3 | `async assess(question, answer) -> Assessment` | Diagnose the answer; return evidence, never a mastery update |
| Learner — DS | `initial_state(concept_ids) -> LearnerUpdate`; `update(state, assessment, history) -> LearnerUpdate` | Pure state calculation; no LLM or storage access |
| Decision policy — DS | `choose(concepts, assessment, candidates, history) -> Optional[Decision]` | Pure, authoritative intervention choice; null means complete |
| Teaching — SWE4 | `async teach(decision, assessment, concepts, presentation_preferences) -> TeachingResult` | Format the selected response using LearnerPresentationPreferences; catalog/provider dependencies injected at startup |

The coordinator takes the session's question, answer, learner state and history, then calls assess → update → choose → teach. It returns the new state and response. When the policy returns null, Teaching accepts that null decision and returns a fixed completion message, keeping the four-stage trace intact. It must not compute assessment, math or decision logic itself. Pass ordinary typed values; no services, queues or framework are needed between these seams.

The API also accepts `presentation_preferences`, normalizes it to LearnerPresentationPreferences, and passes it through the coordinator only to `teach`. Missing object or fields default to false; accept boolean values only. Step-by-step and concise may both be true: return short numbered steps. Preferences must not enter LearnerState, evidence/history, Assessment, or policy inputs. For the same state/evidence, changing preferences must leave all estimates, uncertainty, counts and the Decision unchanged; Teaching must preserve the selected next_question_id.

Initialization returns both state and display estimates, with evidence_applied false, so the API never calculates model statistics. The update result also supplies evidence_applied for history; the coordinator does not infer evidence rules.

SWE1 wires dependencies in one place. The fake implementations occupy the same seams as the real ones. A replacement PR changes the module implementation and its tests, not the coordinator's call signature. Any new feature requiring a field or signature change is a separate, explicit contract change reviewed with affected callers; “stable” does not mean silently adding fields.

## Tiny HTTP surface

| Endpoint | Request | Response |
| --- | --- | --- |
| `POST /api/v1/sessions` | Optional `SessionRequest: {course_id?: string|null}`; empty/absent body supported | `session_id`, `course_id: string|null`, `question: PublicQuestion`, `concepts` |
| `POST /api/v1/turns` | `session_id`, `question_id`, `answer: string`, optional `presentation_preferences: LearnerPresentationPreferences` | TurnResponse below |

The course/session foundation adds optional course ownership. Omitted/null
`course_id` preserves demo behavior. A registered course creates a **preview-only**
session with its first public question and initial concept estimates; unknown IDs
return 404 without creating state. Course turns return 409 before demo catalog
lookup or Coordinator execution. Uploaded-course learning is not activated.
Reset creates a new session: send the same `course_id` to retain course selection;
omit it (or send null) to return to the demo. Existing sessions are unchanged.

`PublicCourse` contains only `course_id`, `title`,
`concepts: [{concept_id, display_name}]`, `source_filenames` and `question_count`.
It is an explicit metadata projection available through the private course catalog;
no discovery/upload HTTP endpoint is added. It omits summaries, source quotes,
answer keys, rubrics, explanations, processing warnings and provider prompts.
See [course/session foundation](COURSE_SESSION_FOUNDATION.md) for private lookup,
adapter, persistence and later activation boundaries.

The answer is a choice ID in G1. Free text can use the same string when supported by reviewed questions after G1. A random session ID held in browser memory and a backend dictionary are sufficient for local synthetic-data G1; this alone is not authentication. Restarting either side may require a reset. No cookies, token hashing or refresh endpoint is required for the anonymous path.

Post-G1, real login is layered on top without breaking that anonymous baseline: `POST /api/v1/sessions` optionally accepts a `Authorization: Bearer <Cognito ID token>` header. When present and Cognito is configured (`COGNITO_USER_POOL_ID`/`COGNITO_APP_CLIENT_ID` set), the backend verifies the token's signature and claims via JWKS and ties the new session to the token's `sub`. When absent, or when Cognito isn't configured, the session stays anonymous exactly as before — this keeps G1's tests and dummy loop unaffected.

Keep the learner's chosen preferences in browser memory and send the current values with each turn. Changes affect the next teaching response; they do not submit/regrade an answer or require a new endpoint. New-session/reset preserves these browser choices; a page reload may restore defaults. No server-side preference persistence is required. Teaching provenance is the additive G2 response extension described above.

TurnResponse fields: `session_id`, `assessment` (the outcome, misconception and feedback only), `concepts`, `decision` (candidate ID, concept, kind and reason, or null), `tutor: {text,fallback,teaching_source}`, `next_question: PublicQuestion|null`, `mode` (dummy/live), `provider` (fake/bedrock), and `trace: list[string]`.

G1 trace can simply be `['assess','update','select','teach']`. Null next_question means the short activity is complete. The UI renders a fixed completion message and offers reset. The live provider/model and detailed candidate scores can be exposed through a reviewed additive extension in G2; no tracing infrastructure is necessary for G1.

Unknown session/question/choice or malformed input may use a simple 400/404/422 with a readable message. No structured retry/error taxonomy, stale-state protocol or automatic retry is required. The backend uses its own catalog question and answer key rather than trusting client-supplied grading data. A disabled submit button is sufficient for the sequential baseline; concurrency guarantees are explicitly absent.

## State and fallback

Keep `session_id -> {question_id, learner_state, history}` in API-owned memory. State access goes through small `new_session`, `load_session` and `save_session` helpers in `backend/app/storage/`; no repository framework, transaction abstraction or persistence protocol. SQLite can replace these helpers when useful without changing the four module callers. No persistence/restart promise in G1.

Post-G1, `backend/app/storage/dynamo.py` implements the same three helpers against a DynamoDB table (one item per session, partition key `session_id`), selected in `main.py` only when `DYNAMODB_TABLE_NAME` is set. Unset, `main.py` keeps using `MemoryStore` exactly as in G1 — the callers (coordinator, routes) never change either way.

Use one fixed fallback teaching response for unclear input and set `fallback=true`. Do not build provider or storage failure simulators. In G2/G3, actual provider timeouts should take a bounded, visible curated fallback; avoid silently sending a failed Bedrock request to OpenAI.

## Provider boundary — after G1

SWE3 adds one small `complete(...)` adapter seam for Bedrock, OpenAI and deterministic fixtures when real agent work begins. Assessment and Teaching use it without importing provider SDKs themselves. Agree only the normalized text/JSON and allowlisted tool fields that the first real roles need, and keep provider-specific translation there. Do not build a generic provider framework or tool-call protocol in G1.

The optional Curriculum/Planning role proposes approved Candidate IDs and short reasons inside the orchestration layer after G1. The quantitative policy still selects the Decision. Neither adding a proposer nor switching providers changes the four core module responsibilities.

## Minimum verification

One example payload and a small loop check verify the agreed fields, that all four seams are called, that only the targeted concept's canned estimate changes, and that teaching follows the selected decision. A small replacement test can inject another fake at one seam to demonstrate that callers are unchanged. The core smoke uses the actual API and browser flow. No generated-schema comparison, concurrent request test or elaborate semantic test matrix blocks G1.
