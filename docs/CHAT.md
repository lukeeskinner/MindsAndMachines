# Session study conversation

The Chatbot composer sends `POST /api/v1/chat` with `session_id`, a nonblank
`message` (at most 2,000 characters), and optional presentation preferences.
`ChatResponse` contains `session_id`, the accepted `message`, response `text`, and
`teaching_source` (`bedrock` or `authored`). These are additive shared contracts;
the quiz assessment, learner and policy signatures are unchanged.

The route resolves the course from the saved session. Missing uploaded courses
return 404; they never use the Intro AI catalog. The provider receives an explicit
projection of public flashcard notes, source filenames, current topic, observation
counts, unresolved review focus, and the last twelve successful chat exchanges.
It receives no question choices, trusted identity fields, private answer keys,
rubrics, raw source records or learner parameters. Conversation is data, not
instructions. The service never calls the assessor, updates the learner, or
selects interventions.

Bedrock mode makes one bounded real provider call (at most twelve seconds) through
the existing adapter, requesting a structured text response. Response size, shape,
duplicate fields, explicit prompt disclosure and control/answer-choice claims are
checked before display. These checks are not a general proof of prose correctness.
Provider or validation failures return a safe 503; the browser retains the draft
for retry. There is no silent live fallback. Fake/local mode explicitly returns
local study notes without invoking a provider.

The API/storage layer owns the bounded conversation history. Quiz writes preserve
it; reset creates a new session with empty history. Dynamo serialization supports
chat history and defaults missing legacy fields to an empty list. The browser
keeps its displayed transcript while navigating between views, orders chat replies
with quiz explanations, and clears it on successful reset or course change.
Reload recovery is not implemented, consistent with the existing session UI.

A per-session guard rejects overlapping quiz/chat writes with 409 and releases on
failure or cancellation. The UI disables duplicate sends and conflicting quiz/reset
controls while a request runs. This guard supports the existing single-process local
demo; it does not provide distributed locking or HTTP idempotency across workers.
The existing anonymous session-ID access model is unchanged.

Verification: `tests/integration/test_chat.py`, Dynamo round-trip coverage,
`frontend/tests/chatbot.test.tsx`, course isolation and study transition tests,
`make check`, `make smoke`, and the real Calculus browser walkthrough recorded in
`DEMO_HARDENING_REPORT.md`. Logs identify successful calls with
`chat_result provider_attempted=True teaching_source=bedrock reason=accepted`.
