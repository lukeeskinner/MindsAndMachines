# Five-person ownership

Role names are placeholders for people, not GitHub accounts. The Phase 1 architect is authorized to revise this documentation. During G1, all five teammates build/review together on one baseline branch through one primary coding-agent implementation session controlled by SWE1; that session may edit all needed paths. The map below governs separate feature work only after G1 acceptance. No parallel implementation sessions or branches during G1.

## Path ownership

| Role | Owns after the dummy baseline | Delivers |
| --- | --- | --- |
| SWE1 — integration lead | Root files; `docs/`; `.github/`; `contracts/`; `scripts/`; `infra/`; `backend/pyproject.toml`; `backend/uv.lock`; `backend/app/main.py`; `backend/app/api/`; `backend/app/storage/`; `backend/tests/api/`; `tests/integration/`; `tests/e2e/`; all unlisted paths | Runnable main, API/state helpers, minimal shared types, review/merges; CI and deployment when useful |
| SWE2 — learning experience | `frontend/` including frontend dependencies, lockfile and UI tests | Accessible question/feedback screen, concept intervals, “Why this next?”, error/retry UX |
| SWE3 — diagnosis and orchestration | `backend/app/agents/`; `backend/tests/agents/` | Bounded coordinator, assessor, provider adapters, budgets and traces |
| SWE4 — teaching and educational quality | `backend/app/teaching/`; `backend/tests/teaching/`; `content/`; `evals/` | Tutor/tools/verifier, authored items, rubrics, sources and educational evaluation |
| DS — learner state and decisions | `backend/app/learner/`; `backend/app/policy/`; `backend/tests/learner/`; `backend/tests/policy/` | Bayesian model, policy, uncertainty, analytic fixtures and model explanation |
| Claude (AI session) — AWS/DevOps groundwork | Local AWS CLI/credential configuration, read-only or single-call AWS verification, the `backend/app/agents/` provider-adapter seam, and the `backend/app/storage/dynamo.py` persistence seam | Confirmed account, region and Bedrock model access; a provider adapter and a DynamoDB-backed storage option, both selected only via explicit env vars so the G1 defaults (fake provider, in-memory storage) are unchanged when unconfigured |

The user, acting as the project owner/Phase 1 architect, has explicitly authorized the Claude row above as a scoped exception to the general G1/G2 gate in WORKSTREAMS.md and the "no real model/provider calls" line in AGENTS.md: AWS account setup, CLI verification, and building the provider-adapter and DynamoDB storage modules themselves. The G1 dummy loop stays intact — FakeAssessor/FakeLearner/FakePolicy/FakeTutor remain the default composition, and `backend/app/main.py` uses MemoryStore unless `DYNAMODB_TABLE_NAME` is explicitly set; the new modules are additive, not forced onto the live turn path.

Ownership includes additions, deletions and renames. A rename crosses both source and destination owners. A new unlisted directory is integrator-owned until the map is explicitly revised. Ownership is permission to implement within an assigned task, not permission to start any feature at any time.

Contracts are SWE1-owned even when they primarily serve one module. DS proposes statistical changes; SWE4 proposes content fields; neither edits shared schemas silently. Module documentation may live in the owner's directory. Shared architecture and status updates go through SWE1 to avoid five agents editing the same files.

## Preventing overlap

After baseline acceptance, record each small deliverable in an issue or PR: role/person, branch, base main SHA, paths and acceptance condition. SWE1 agrees assignments in a short team sync. Check active work and open PRs before starting; use draft PRs to make changes visible.

A short issue or PR description is sufficient for the claim; no exclusive-lock service or automated claim enforcement. Role ownership is broad; the active claim is narrow. If one person runs multiple coding sessions, give them nonoverlapping subpaths and separate worktrees. Do not let two agents work in the same checkout. Avoid a shared editable task-board file for every contributor; WORKSTREAMS.md gives the roadmap, GitHub issues give live status.

If paths collide, the second task pauses edits on those paths, shares the proposed change with the owner, and continues independent work. Prefer an owner-authored prerequisite PR. A cross-owner exception must identify exact paths and purpose in the claim and PR; it expires when that PR merges. No permanent “touch anything” exception.

## Review first; automation only when useful

Use the seven-check preflight in CONTRIBUTING.md: branch, current main comparison, path ownership, contract warning, conflicts, check command and core smoke. Manual path review against this table is enough. SWE1 reviews feature PRs; another SWE reviews SWE1-authored PRs. All five review the running baseline before G1 is accepted.

CODEOWNERS, automatic path enforcement and branch-protection configuration are optional later conveniences. Do not require a trusted-base rule loader, role authorization metadata, multiple CI jobs or a special review-bypass design for the hackathon MVP. If CODEOWNERS is added later, use real handles and check its actual approval behavior; never claim prose instructions are enforced permissions.

AGENTS.md supplies shared coding-session guidance; CLAUDE.md imports it. Neither these files nor the ownership table is a filesystem sandbox. Small tasks, one owner per active path and integrator review are the practical coordination mechanism.
