# Heuristics demo content

This catalog keeps the six existing concept IDs and expands only
`admissibility_vs_consistency`. The original two questions, worked example,
candidate, and its four presentation variants are unchanged.

| Candidate | Kind | Content | Follow-up |
| --- | --- | --- | --- |
| `relationship-example` | `worked_example` | `heuristic-distinction` | `relationship-q02` |
| `relationship-probe` | `diagnostic_probe` | `heuristic-distinction-probe` | `relationship-q03` |
| `relationship-hint` | `socratic_hint` | `heuristic-distinction-hint` | `relationship-q04` |

The probe requests separate judgments without definitions, computations, or a
conclusion. Its follow-up distinguishes the misconception that an admissible
heuristic must also be consistent: all remaining-cost bounds pass, but one edge
constraint fails. Choosing "both" is evidence relevant to that misconception,
not a conclusive diagnosis on its own.

The hint asks the learner to consider the edge cost and neighboring estimate as
well as remaining path costs. It gives no graph arithmetic or classification.
Its follow-up satisfies both properties, so learners must check the conditions
instead of repeating the worked example's conclusion.

All four presentation variants carry the same task. The existing Tutor can
render these short prompts as a single numbered step. Answer keys and rubrics
stay server-side.

## Content review notes

For each directed graph, G is the goal, there are no other edges, all costs are
positive, and the goal heuristic is zero. Tuples below use node order S, A, G.

| Question | Edge costs S-A, A-G, S-G | Heuristics | Shortest remaining costs | Classification / key |
| --- | --- | --- | --- | --- |
| `relationship-q03` | 2, 4, 7 | 5, 1, 0 | 6, 4, 0 | Admissible, inconsistent / a |
| `relationship-q04` | 2, 5, 8 | 6, 4, 0 | 7, 5, 0 | Admissible, consistent / a |

For q03, the S-A check fails because 5 > 2 + 1. For q04, all checks pass:
6 <= 2 + 4, 4 <= 5 + 0, and 6 <= 8 + 0. Tests extract the displayed values and
independently recompute the classifications. These are author checks; teammate
educational review remains part of the handoff.

## Runtime behavior and verification

Existing AdaptivePolicy scores naturally select a hint after the original first
wrong answer, a probe under high uncertainty without a misconception signal,
and an example for sufficiently weak, diagnosed performance. No scores change.
The policy filters previously used candidate IDs. Each candidate therefore has
a distinct destination, and no destination is the initial question.

One repeatable local walkthrough is q01/a -> hint -> q04/a -> probe -> q03/a ->
worked example -> q02/b -> completion. Correct/incorrect/unclear response paths
all exhaust the three candidates without repeating a question. The old
worked-example-only fixture remains a separate regression test, not the default
expanded selection sequence.

`make check` includes catalog integrity, graph answer checks, all Tutor preference
combinations, mocked provider validation, policy eligibility, and API flows.
`make smoke` exercises the expanded sequence over real local HTTP, including
reset and presentation preference isolation. No live AWS calls are needed.

Integration notes: FakeAssessor's feedback and misconception label remain generic
to the relationship concept.
The inactive RealAssessor grades the new answer keys, but its diagnosis allowlist
still covers only q01/q02; new items receive no named misconception from it.
Reviewing and extending that allowlist is a later RealAssessor activation task,
outside this content expansion.
The current contracts have no assisted-answer flag: a selected hint introduces a
fresh follow-up, rather than a hint request on an already active question. These
runtime/documentation limitations are unchanged by this content-only workstream.
