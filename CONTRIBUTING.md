# Hackathon integration workflow

Status: G1 has working setup/dev/check/smoke commands. CI and GitHub protection automation remain deferred. Use the seven-check preflight manually; do not merge the baseline into main under the current task authorization.

## Bootstrap and the single baseline

Reconciliation is complete: origin is `https://github.com/lukeeskinner/MindsAndMachines.git`, default branch main, approved documentation base `5ecaecf`. The user intentionally bootstrapped the empty remote; this implementation preserves that history. Do not invent a remote or force-push an unrelated root history. For an empty remote, seed the reviewed documentation when authorized; otherwise use its normal documentation PR. This guide calls the intended canonical branch main; verify the actual default first.

After explicit Phase 2 approval, use **one `codex/baseline` branch and one primary coding-agent implementation session controlled by SWE1**. All five teammates participate in building/reviewing that session's work. No parallel implementation branches or coding sessions until G1 is accepted. SWE1's baseline session may edit all required module paths. A second SWE reviews the baseline and all five review the running loop. Stop for that review now: no push/merge to main is authorized. A later authorized main merge and team acceptance precede feature work.

G1 acceptance is exactly PHASE2.md. GitHub configuration, CI jobs and preflight scripts are not substitutes for, or blockers to, the working loop.

## After G1

1. Agree a small task, role and exact paths with SWE1; record them in an issue or PR. Check for overlap with the team's active work.
2. Fetch main and use a short-lived `codex/<role>-<task>` feature branch from it. Give concurrent coding sessions separate worktrees/checkouts and nonoverlapping paths.
3. Make one coherent change behind the stable seam. Open a draft PR early. Request a shared contract change before making other modules depend on it.
4. Perform the seven-check preflight below; push and obtain SWE1 review. A second SWE reviews/merges SWE1-authored changes. Domain owners help review their module.
5. Merge, run the core smoke on main, and synchronize before the next increment. Revert a broken feature promptly through SWE1 rather than allowing main to remain broken.

Prefer small increments and frequent integration over five large end-of-event merges. Merge current main into active branches when necessary; never overwrite someone else's uncommitted work or force-push shared main. The claim can be a short issue/PR description, not a lock service or metadata authorization system.

## MVP preflight — seven checks only

This is a checklist first. SWE1 may later wrap it in a short script. G1 implements the small check/smoke commands documented in README.md.

| Check | Simple method |
| --- | --- |
| Correct branch | `git branch --show-current` and `git status --short`; use `codex/baseline` for G1, the assigned feature branch after G1, never accidental work on main |
| Fetched/current main comparison | Explicitly `git fetch origin`, then `git rev-list --left-right --count origin/main...HEAD`; inspect and integrate changes when behind before merging |
| Ownership/path violation | Review committed diff plus staged, unstaged and untracked files against OWNERSHIP.md and the agreed task; include both paths of renames; resolve out-of-scope edits with SWE1 |
| Shared-contract modification warning | Flag changes to `contracts/` and public signatures for SWE1 and affected owners; review the example response together; no generated-diff pipeline required |
| Merge conflict detection | Use GitHub's mergeability indicator against current main, or attempt the main merge in a clean feature checkout; resolve conflicts before merging, never merge into unrelated dirty work |
| Tests/check command | Run the documented `make check`: a small backend loop check and frontend typecheck/build |
| Core smoke test | Run the documented `make smoke` API sequence and the short manual browser walkthrough; use browser automation only if already easy |

Missing main/remote information is reported as unverified rather than passed. An offline session can keep working within agreed scope, but must refresh the main comparison before merge. Any failed functional check or unresolved conflict blocks the merge; a shared-contract warning requests review, not a new enforcement platform. For the first seed commit to a truly empty remote, a main comparison is inapplicable and should be recorded that way.

Do not add PR-path intersection analysis, trusted-base rule loaders, Git object simulations, machine-readable ownership authorization, merge queues or a role/claim CLI to the MVP. The path map and integrator review are sufficient. Basic secrets hygiene still applies to all work; it does not require another preflight subsystem.

## Commands and CI

Implemented commands:

| Command | Purpose |
| --- | --- |
| `make setup` | Install pinned project dependencies with documented prerequisites |
| `make dev` | Run frontend/backend in deterministic mode by default |
| `make check` | Small backend loop check and frontend typecheck/build; add relevant module tests with real replacements |
| `make smoke` | Minimal new-session → answer → response → reset API sequence; pair with a documented browser walkthrough |

After setup, dummy runtime/checks require no cloud keys. No `generate-contracts` or automated `preflight` target is mandatory. One optional GitHub Actions job can run check and smoke using dummy mode. If CI setup consumes baseline time, run the same commands locally and add the job after G1. Multiple jobs, CODEOWNERS enforcement and elaborate protection settings are stretch work. Use normal PR review from the start; add simple protections only when easy and available.

If CI is added, do not give untrusted PR code secrets. Live Bedrock smoke runs separately on trusted code with the team's authorized credentials during G2/G3; it does not block credential-free development.

## Shared changes and handoff

SWE1 owns common types, fixtures and wiring. Discuss an exact field/signature change and its callers before landing it; update the small Python/TypeScript types and example together. Handwritten types are allowed. Record a narrow cross-owner exception in the issue/PR when needed; no elaborate approval metadata is required.

The PR should say what changed, which paths/contract changed, which check and smoke were run, and anything still unverified. For documentation-only changes, report relevant document checks; application changes require the check and core smoke. Do not call an unavailable test a pass or make a later stretch test an implicit G1 requirement.
