# Real Assessor review notes

`real_assessor.RealAssessor` implements the existing async `assess(question,
answer) -> Assessment` protocol. It is selected by `main.py`; `FakeAssessor` remains available for tests.
No shared records or seam signatures change.

The server compares a valid submitted choice ID exactly with `Question.answer_key`.
Correct and incorrect choices yield scores 1 and 0. `unsure`, `unscorable`, missing
or unknown choices, and questions without a usable answer key yield unclear/null.
They bypass the provider and BayesianLearner applies no evidence for them.

Fake/default/local mode returns deterministic feedback with no provider call.
Unsupported provider selections do the same; there is no provider switching.
In Bedrock mode, one call may enrich only misconception and feedback. The prompt
contains the public question, submitted choice, trusted outcome and allowed
diagnosis IDs. Private rubrics and the answer-key field are withheld.

The only reviewed diagnosis is `admissible_means_consistent`. The local/fallback
mapping is deliberately choice-specific and requires the relationship concept:

- q01/a explicitly asserts that every admissible heuristic is consistent.
- q02/a classifies an admissible but inconsistent heuristic as both.
- q03/b makes that same error. Its rubric explicitly links that distractor to
  confusing the total-cost bound with the edge constraint (5 > 2+1).
- q03/c and all q04 choices receive no diagnosis. q04 really is consistent
  (6 <= 2+4, 4 <= 5+0, 6 <= 8+0); its incorrect answers do not establish this
  misconception. No new taxonomy is introduced.

These reviewed signals preserve the existing golden smoke's first-answer diagnosis
and feedback. They replace RealAssessor's previous blanket null in local/fallback
mode and FakeAssessor's blanket diagnosis on every wrong answer. A wrong q04
answer can consequently select a different intervention; policy scoring is unchanged.
Bedrock may attach only the diagnosis allowed for that question/choice or abstain.
Unknown question IDs and other concepts get null diagnosis even when the model
requests one; valid Question objects still grade from their own answer keys.
Correct/unclear responses always have null diagnosis. Generated-course routes
remain outside this workstream; an eventual listed unsure choice already works
through the existing Question/Assessment contract.

Output must be strict JSON with exactly `misconception_id` and `feedback`. Duplicate
keys, non-JSON constants, invalid types, blank feedback, excessive lengths, control
fields and detected leakage are rejected. Feedback is limited to 500 characters;
the entire JSON response is limited to 4096 characters. Checks cover explicit
answer labels, correct-choice text, copied private rubric/system excerpts,
internal IDs and control language. These conservative lexical checks can reject
benign prose and cannot prove arbitrary paraphrases safe or pedagogically accurate.
They never determine the authoritative score, outcome or concept.

Provider errors, adapter deadlines, malformed output, validation rejection and
unexpected exceptions return the same deterministic feedback and trusted grade.
No retry or alternate provider is used. Caller-owned question data is copied before
the await; no state is retained. Error payloads and prompts are not logged.

Runtime deadline design:

- Coordinator sets an 18-second total asynchronous deadline. Its provider budget
  is task-local and restored on exit, including cancellation.
- Assessment has a 4-second provider cap; Tutor has a 12-second cap. They run
  sequentially, once each. Every provider call uses the minimum of its configured
  timeout, stage budget and remaining total budget, including SDK socket settings.
- `BEDROCK_TIMEOUT_SECONDS` still defaults to 12 and accepts (0, 15]. Smaller
  settings remain effective; larger ones cannot extend a runtime stage.
- The usual double timeout returns HTTP 200 with trusted grading/evidence and
  authored teaching fallback within about 16 seconds. No diagnosis retry occurs.
- If a replacement seam stalls beyond the total deadline, the route returns a
  generic 504 without saving partial state/history. No automatic turn retry occurs.
- Two seconds remain for local work and another two before the browser's existing
  20-second timeout. No frontend change is needed. Synchronous storage/network
  delays and event-loop blocking are not preempted by an asyncio deadline.
- Timed-out SDK threads may finish later; their results cannot update the turn.
  SDK socket deadlines and disabled retries remain in place.

Assessment still has no provenance field; the existing public provider/teaching
source labels describe teaching only. No UI or contract extension is added.

Run the focused suite with `PYTHONPATH=. backend/.venv/bin/python -m unittest
backend.tests.agents.test_real_assessor -v`. `make check` also discovers it. Provider
calls are mocked, including a timed-out adapter worker; no live AWS access is tested.
