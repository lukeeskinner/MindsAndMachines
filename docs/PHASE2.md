# Phase 2 / G1 — prove the replaceable loop

**G1 implementation is authorized and technically verified on `codex/baseline`; team review remains pending. Do not merge into main or begin G2.** The user approved the simplified plan and the presentation-preference placeholder. G1 exists only to prove that the following loop works through independently replaceable modules:

```text
browser → API → fake assessment → fake learner → fake decision policy
        → fake teaching → response → browser
```

The coordinator is a few in-process calls behind the API. The browser uses the real API; it must not manufacture the backend response. All educational intelligence is deterministic fake behavior in G1. No real Bayesian arithmetic, policy scoring, agent tool loops or model calls.

## One team, one branch, one implementation session

All five teammates build/review the baseline together. SWE1 controls **one baseline branch (`codex/baseline`) and one primary coding-agent implementation session**. SWE2 guides the screen, SWE3 guides the assessment/coordinator seam, SWE4 supplies the small teaching example, and DS reviews learner/policy inputs and canned outputs. The primary session makes the integrated edits; there are no independent implementation sessions, delegated coding agents or five feature branches during G1.

This baseline session may touch every path needed for the slice. The five-role ownership map takes effect for separate feature work only after G1 acceptance. Everyone reviews the same running loop before that split.

## Smallest build order

1. Agree the short data shapes and function signatures in CONTRACTS.md. Write one shared example response and minimal Python types; a small handwritten TypeScript counterpart is fine. Generate types only if existing tools make it nearly free.
2. Wire API → coordinator → the four fake modules. Use a small in-memory session dictionary, unless a few straightforward SQLite operations are equally quick. Keep state access in the API/storage layer.
3. Add one browser screen: question, answer submission, tutor response, concept estimates, selection reason, and new-session/reset. Display deterministic mode. Disable the submit button while one request is pending; assume sequential use.
4. Add one small backend loop check and document one command to run checks. Add a core smoke path against the real API, with a browser walkthrough. A browser automation script is welcome only if quick to add.
5. All five teammates review the running slice; a teammate follows the setup instructions from a fresh checkout. Stop for review on `codex/baseline`. The current user instruction prohibits merging into main. A future, explicitly authorized merge and team acceptance must happen before separate feature workstreams.

A single CI job may run the same checks if easy to configure. CI setup, branch-protection configuration, schema generation and preflight automation are not G1 acceptance blockers. Manual review and the short preflight checklist suffice.

## Small presentation-preference placeholder

Include three ordinary labeled checkboxes on the existing screen: plain language / explain jargon, step-by-step, and concise. Keep their explicit choices in browser memory and send them with the next turn only to fake Teaching via the API/coordinator. The fake uses simple canned wording/formatting (short numbered steps when both step-by-step and concise are selected). No new settings page, endpoint, persistence, agent or workstream. Reset creates fresh knowledge state while retaining browser choices.

Use semantic controls, keyboard focus, readable contrast, scalable text and reduced-motion support as normal UI practices, not identity-based modes. Never infer disability, demographic identity or mastery from preference choices.

In the existing smoke walkthrough, repeat the same answer sequence from fresh sessions with one preference changed: teaching presentation differs while concept estimates, intervals, evidence counts, selected intervention and next question match. This is one small comparison, not a preference-combination test matrix. No real math or new provider call is needed.

## Golden scenario

Keep six concept IDs so later UI/model work has the right shape, but only two questions and one authored explanation are needed for the first loop. Return canned values by lookup rather than implementing mathematics.

| Step | Required behavior |
| --- | --- |
| Start | New session; six concepts at mean 0.5, interval [0.05,0.95], count 0; first relationship question |
| Answer incorrectly | Fake assessment identifies the relationship misconception; fake learner changes only that concept to mean 1/3, interval about [0.0253,0.7764], count 1 |
| Adapt | Fake policy chooses `worked_example` with a short reason; fake teaching returns the explanation and a fresh question |
| Answer correctly | Fake learner returns canned mean 0.5, interval about [0.1354,0.8646], count 2 for that concept; other concepts remain unchanged; finish or return a canned next probe |
| Reset | New session restores the initial values and first question |

Private state can use canned `(alpha,beta)` tuples `(1,1)`, `(1,2)`, `(2,2)`. These are fixtures, not real updates. One unknown/unclear-answer path may return unchanged state and a fixed “Let's try another example” response marked as fallback. No failure simulator or provider mock framework is needed.

## G1 acceptance — only these checks

- A teammate can start the app using the documented local command without cloud keys after dependency setup.
- The browser completes the golden loop through the API and all four fake boundaries; a simple stage list or test spies demonstrate those calls.
- The response displays the canned concept change, chosen intervention/reason and teaching text. The preference placeholder changes delivery only, as checked by the small comparison above. Each module has the agreed callable interface so its implementation can be replaced independently.
- New-session/reset works. In-memory state lost on backend restart is acceptable and documented.
- The small check command and core smoke pass. All five teammates review the baseline before team acceptance; this human review remains pending. Record the review branch SHA now; no main merge or accepted-main SHA is authorized in this task.

The smoke may be an API sequence plus a short manual browser walkthrough; a fully automated browser suite is not required. Do not mark unimplemented checks as passed, but do not invent additional gate requirements.

## Explicitly later, never G1 blockers

| Work | Earliest useful point |
| --- | --- |
| Real Beta–Bernoulli model, explainable scoring, meaningful agents and Bedrock | G2 replacements after baseline acceptance |
| SQLite persistence and refresh/restart recovery | G2 if useful; G3 only if the chosen demo needs persistence |
| Hint/assisted-answer tracking and richer content checks | G2 when those interactions are added |
| One CI job and a short preflight script | G2 if they save time; manual equivalents remain valid |
| Concurrent requests, elaborate idempotency and stale-version conflicts | Stretch; add only if actual usage requires them |
| Storage-failure simulation, provider-failure matrix, full browser error coverage | Stretch; rehearse one real provider fallback in G3 |
| Secure sessions/public-access controls | G3 if externally accessible or real data is introduced |
| CODEOWNERS automation, sophisticated Git analysis, multiple CI jobs | Stretch; not required for the hackathon MVP |
| Generated client/schema pipeline | Optional if nearly free; not a dependency of any gate |

The implemented G1 commands and browser walkthrough are in README.md. Stop after technical verification and wait for review. G2 and any merge into main require later authorization.
