# Real Assessor review notes

`real_assessor.RealAssessor` implements the existing async `assess(question,
answer) -> Assessment` protocol. It is not imported or selected by `main.py`;
the running application still uses `FakeAssessor`. No shared records change.

The server compares a valid submitted choice ID exactly with `Question.answer_key`.
Correct and incorrect choices yield scores 1 and 0. `unsure`, `unscorable`, missing
or unknown choices, and questions without a usable answer key yield unclear/null.
They bypass the provider and BayesianLearner applies no evidence for them.

Fake/default/local mode returns deterministic feedback with no provider call.
Unsupported provider selections do the same; there is no provider switching.
In Bedrock mode, one call may enrich only misconception and feedback. The prompt
contains the public question, submitted choice, trusted outcome and allowed
diagnosis IDs. Private rubrics and the answer-key field are withheld.

The only existing authored diagnosis is `admissible_means_consistent`, currently
embedded in FakeAssessor rather than catalog metadata. It is allowed only for
incorrect responses on the two reviewed relationship questions and their concept.
Unknown IDs become null. Correct/unclear responses and all fallbacks have no
misconception. New questions need a reviewed vocabulary mapping before enrichment
can attach a diagnosis; ordinary answer-key grading still works.

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

Before separately authorized activation, SWE1 should review:

- The composition-root substitution and both local and mocked live turn flows.
- The combined latency budget: assessor and Tutor would call the shared adapter
  sequentially. Two default 12-second deadlines exceed the browser's 20-second
  request budget; use a suitably smaller configured deadline or a reviewed total
  turn budget at integration time.
- Whether assessment provenance needs a later contract/UI addition. Assessment
  has no provenance field; the existing public provider label describes teaching.
- The intentional conservative null diagnosis in local/fallback mode, which can
  alter the policy's diagnosis signal after activation even though grading is fixed.

Run the focused suite with `PYTHONPATH=. backend/.venv/bin/python -m unittest
backend.tests.agents.test_real_assessor -v`. `make check` also discovers it. Provider
calls are mocked, including a timed-out adapter worker; no live AWS access is tested.
