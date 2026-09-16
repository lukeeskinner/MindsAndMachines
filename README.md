# Minds & Machines — Adaptive AI Tutor

An adaptive tutor that diagnoses an answer, updates a concept-level learning estimate, chooses an intervention, and explains that choice to the learner.

**Status: core architecture supported by the user; implementation plan simplified for hackathon speed. Documentation only. Phase 2 is not approved, and there is no runnable application, CI or deployment.**

## Start here

1. Coding agents: read [AGENTS.md](AGENTS.md).
2. Product and technical decisions: [architecture](docs/ARCHITECTURE.md).
3. Stable interfaces: [contracts](docs/CONTRACTS.md).
4. Your scope and current work: [ownership](docs/OWNERSHIP.md) and [workstreams](docs/WORKSTREAMS.md).
5. Integration rules: [contributing](CONTRIBUTING.md).
6. First implementation: [Phase 2 baseline](docs/PHASE2.md).
7. Cloud choices: [AWS strategy](docs/AWS.md).
8. Demo and evaluation: [demo plan](docs/DEMO.md).

Each topic has one authoritative document. CLAUDE.md imports AGENTS.md; do not maintain two rule sets. The attached brainstorm informed the design but is not a service checklist.

## Repository inspection — 2026-09-16

- Local Git repository exists; HEAD points to `refs/heads/main`, which has no commits.
- No tracked project files, working files, local feature branches, or configured remotes existed before this work.
- Git metadata includes a Codex capture reference to the empty tree and sample hooks; neither is application history nor an installed integration check.
- Local configuration contains ordinary repository settings (including case-insensitive filenames); no remote/branch tracking or custom hooks path was found. `gh` was not available on PATH.
- The brief says an existing GitHub repository is the source of truth. Its URL, contents, default branch, permissions, protections, and Actions availability have not been verified. Do not assume GitHub is empty because this checkout is empty.
- Phase 1 creates only the Markdown files listed below. No commit, push, branch creation, Git configuration change, dependency installation, model invocation, or deployment was performed.

## Chosen shape

React + TypeScript UI; one FastAPI/Python backend; in-process orchestration, assessment, teaching, learner model and policy modules; curated concept/question files; in-memory state for G1, with simple SQLite only when useful. Bedrock is the intended live inference provider. Local deterministic mode requires no cloud credentials. The future AWS deployment uses the same app on one EC2 instance if hosting is needed/feasible. Agent Toolkit for AWS is development tooling for Codex/Claude, not a runtime tutor component. Cognito and other infrastructure stay deferred unless event requirements justify them.

G1 proves only browser → API → fake assessment → fake learner → fake decision → fake teaching → response → browser, plus reset. All five teammates build/review together using one baseline branch and one primary coding-agent implementation session controlled by SWE1. Feature branches begin only after acceptance.

The mathematical MVP uses a Beta distribution per skill to estimate success on comparable unaided questions, with uncertainty. The UI calls this a **mastery estimate**, explains the proxy, and never presents it as a validated measure of knowledge. The next-action policy is an explicit heuristic; it is not claimed to estimate causal learning gain.

## Files created in Phase 1

```text
.
├── README.md
├── AGENTS.md
├── CLAUDE.md
├── CONTRIBUTING.md
├── .github/
│   └── pull_request_template.md
└── docs/
    ├── ARCHITECTURE.md
    ├── CONTRACTS.md
    ├── OWNERSHIP.md
    ├── WORKSTREAMS.md
    ├── PHASE2.md
    ├── AWS.md
    └── DEMO.md
```

## Proposed application tree — not created yet; G1 creates only its few required files

```text
frontend/                     # SWE2: React/Vite, UI tests, frontend lockfile
backend/
  pyproject.toml              # SWE1: one Python environment and lockfile
  uv.lock
  app/
    main.py                  # SWE1: dependency wiring and static UI serving
    api/                     # SWE1: HTTP/session validation
    storage/                 # SWE1: memory helpers; simple SQLite later if useful
    agents/                  # SWE3: coordinator, assessor; provider adapters after G1
    teaching/                # SWE4: fake tutor first; tools/verification after G1
    learner/                 # DS: belief updates and uncertainty
    policy/                  # DS: intervention selection and explanations
  tests/
    api/                     # SWE1
    agents/                  # SWE3
    teaching/                # SWE4
    learner/                 # DS
    policy/                  # DS
contracts/                   # SWE1: minimal types and examples; generation optional
  fixtures/                  # SWE1: boundary and end-to-end example payloads
content/                     # SWE4: authored catalog, rubrics, provenance
evals/                       # SWE4: educational rubric cases and review results
tests/integration/           # SWE1: module replacement checks
tests/e2e/                   # SWE1: optional browser automation after the manual smoke
scripts/                     # SWE1: check/smoke helpers; other automation optional
infra/                       # SWE1: one-container build and later EC2 runbook
.github/workflows/           # SWE1: one optional credential-free CI job
.github/CODEOWNERS           # Optional later convenience, never a G1 blocker
.gitignore                   # SWE1: credentials, runtime data, builds, worktrees
Makefile                     # SWE1: documented entry points
```

Do not create every directory speculatively. Phase 2 should create only what its working slice uses. Existing Markdown files remain alongside this future tree.

## Next gate

Review the simplified PHASE2.md and explicitly approve Phase 2 before implementation. Supply the GitHub URL so SWE1 can reconcile the existing repository before remote integration. Then build only the small deterministic loop in one branch/session; parallel feature implementation begins after G1 acceptance. No implementation, toolkit installation or deployment is authorized by this revision.
