# Current work and gates

Status: **the user supports the core product, module boundaries, math, local-first AWS approach, ownership and demo concept. The implementation plan has been simplified; Phase 2 is still not approved.** No application, checks or deployment exist. GitHub URL and real team handles remain unconfirmed.

## Gate sequence

| Gate | Work and exit evidence | Current state |
| --- | --- | --- |
| G0 | Review the simplified plan; obtain explicit Phase 2 approval and reconcile the existing GitHub repository | Awaiting Phase 2 approval and remote information |
| G1 | One browser/API loop through four replaceable fakes, new-session/reset, small check and core smoke; team accepts the baseline main SHA | Not started |
| G2 | Small PRs replace fake learner, policy, diagnosis and teaching; improve UI/content; add Bedrock and a small provider adapter | Blocked on G1 |
| G3 | Rehearse live Bedrock demo/fallback; deploy the same app to AWS if required/feasible; add only needed persistence/access controls | Not started |
| G4 | Freeze a demo SHA and rehearse the presentation with a labeled offline backup | Not started |

## G1 collaboration

**All five teammates participate in building/reviewing one baseline branch and one primary coding-agent implementation session controlled by SWE1.** SWE2 shapes the screen, SWE3 the assessment/coordinator seam, SWE4 the teaching example, and DS the model/policy records and canned values. SWE1 directs the integrated implementation. No parallel implementation sessions, delegated coding agents or five feature branches until G1 acceptance.

PHASE2.md is the sole G1 acceptance checklist. Use memory if SQLite slows the loop. No schema-generation pipeline, concurrency protocol, failure matrix, CI topology or governance automation may hold up this gate.

## First post-G1 assignments

| Role | First small replacement/change | Follow-up |
| --- | --- | --- |
| SWE1 | Keep callers/wiring stable and review integrations | Add simple SQLite persistence or one CI job only when useful; later AWS packaging |
| SWE2 | Improve concept estimates, uncertainty and decision explanation on screen | Accessibility and useful error recovery; no exhaustive UI state matrix |
| SWE3 | Bedrock adapter and real Assessment/Diagnosis behind the existing seam | Bounded tools; optional Curriculum/Planning proposer if it adds visible value |
| SWE4 | Reviewed concept/question content and real Tutor implementation | Useful teaching tools and content verification |
| DS | Real Beta–Bernoulli update behind the learner seam | Explainable authoritative intervention policy |

The two core agentic roles are Assessment/Diagnosis and Tutor. A third Curriculum/Planning role may propose approved candidates or remedial paths, but it cannot bypass the quantitative selection policy. SWE3 owns its orchestration code; SWE4 supplies content and DS reviews selection semantics. Do not create eight nominal agents.

## Later work is selective

Add simple persistence in G2 if the demo benefits. Add provider timeout/fallback handling with real inference and rehearse it in G3. Add appropriate access controls only before public exposure/real data. Complex idempotency, concurrency/versioning, failure simulation matrices, full browser error coverage, CODEOWNERS enforcement, sophisticated Git analysis and multiple CI jobs remain stretch work unless a concrete problem makes them necessary. Generated clients/schemas are optional convenience, not a gate.

Aim to finish the first working loop in the first short team build session; do not spend that session constructing enforcement infrastructure. The event duration is unknown, so there is no fixed-hour promise. Use small PRs and frequent integration after G1, and reserve roughly the final 20% for demo rehearsal/freeze. Cut voice/images, bandits and extra courses before the adaptive loop.

## Information to resolve when relevant

- GitHub URL/history/default branch and five human role assignments before remote integration; account handles are not a prerequisite for local loop design.
- Event duration, deadline, official judging rules and actual AWS requirements.
- AWS account/region, allowed Bedrock model/access/quota, credits/spending limit and permission for any hosting work.
- Whether judges need a public URL or presenter-controlled access is sufficient.

Agent Toolkit for AWS belongs to AWS development setup for Codex/Claude, not G1 or the runtime tutor. See AWS.md. Toolkit installation is not part of the present documentation task.

After G1, an issue or PR description with role/person, branch, base main SHA, paths, deliverable and any shared-contract change is enough for a work claim. SWE1 coordinates overlap directly; no machine-readable claim system. GitHub becomes the live source of truth once connected. Update this document at gate changes, not on every commit.
