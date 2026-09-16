# G1 handoff — review branch only

## Git reconciliation

Verified origin: https://github.com/lukeeskinner/MindsAndMachines.git. Remote HEAD is main at `5ecaecfdfa0484c8da18ceff9c6646a2b258f1ea`; local main and the starting codex/baseline matched it. The user intentionally bootstrapped the previously empty remote. No unrelated histories, overwrites, force-pushes, main pushes or main merges were needed. Work stays on `codex/baseline`; `git rev-parse HEAD` identifies the local implementation commit after handoff.

## Implementation

One primary coding session built FastAPI plus React/Vite. The API passes ordinary records through Coordinator → FakeAssessor → FakeLearner → FakePolicy → FakeTutor, saves only in-memory session state, and returns the public response to the browser. The four seams are independently injectable in `backend/app/main.py`. A null decision means fixed completion through FakeTutor. Preferences reach Teaching only.

The two questions concern admissibility versus consistency. The authored example assumes nonnegative edge costs and zero heuristic at the goal. Canned target states are initial `(1,1)`, incorrect `(1,2)`, and then correct `(2,2)` with the exact documented means/intervals/counts. There is no Bayesian computation or policy ranking. All five other concepts stay at the initial values.

## Commands

- One-time setup: `make setup`.
- Start frontend and API: `make dev`; open http://127.0.0.1:5173.
- Backend tests and frontend typecheck/build: `make check`.
- Actual HTTP core smoke: `make smoke`.

See README.md for prerequisites and the exact browser walkthrough.

## Verification

- `make check`: five backend tests passed; frontend TypeScript check and Vite build passed.
- Replacement test: Assessor, Learner, Policy and Teaching each independently substituted behind the same callers.
- Golden test: shared example payload, target-only canned updates, completion, all four trace stages, public question projection and new-session reset passed.
- Preferences test: each of the three options and the combined numbered/concise/plain format altered only teaching; no full combination matrix was added.
- Fallback test: “I'm not sure yet” preserved estimates and returned the one marked curated fallback.
- Input check: preference flags accept booleans, rejecting string coercion.
- `make smoke`: real local HTTP sequence, reset and identical-evidence preference comparison passed.
- Browser walkthrough: A (incorrect), worked example, fresh question, B (correct), completion and reset verified through the real UI/API. Checkbox selections survived reset. Same first-turn estimates were observed with different teaching text; all three enabled produced short plain-language numbered steps.
- The dependency installer reported a Vite advisory; the pin was updated within Vite 7 to 7.3.6, and npm reported zero advisories afterward.
- Fresh-checkout verification: exported the staged source to a separate temporary directory with no existing project environments/node_modules. The exact `make setup`, `make check`, and `make smoke` commands all passed there. This was an agent-run clean source checkout, not a claimed teammate review.

## Deliberate limits and assumptions

Sequential local demo only. No production sessions, request versions/idempotency, concurrent-write guarantees, database, failure simulator, generated-client pipeline or CI jobs. State is discarded on backend restart; reset is the recovery path. Non-golden answers are deterministic placeholders rather than a general learner model. Native runtime scripts target macOS/Linux; Windows can use WSL but was not tested. Percentage display rounds to one decimal; API fixtures retain the agreed values.

All source and runtime dependencies are local web/API tooling. There are no real LLM/provider calls, no Bedrock/OpenAI SDKs or calls, no AWS tooling/runtime integration, deployment, authentication, real math, real scoring, additional agent roles or G2+ features. The future provider label in the architecture is not an implemented adapter.

Human review by all five teammates and a teammate-run checkout are still pending. The agent's clean-checkout run is technical verification, not a substitute for that review. No accepted-main SHA or team acceptance is claimed. Stop on the review branch; do not merge or start G2.

## Full relevant tree

```text
.
├── .github/
│   └── pull_request_template.md
├── .gitignore
├── AGENTS.md
├── CLAUDE.md
├── CONTRIBUTING.md
├── Makefile
├── README.md
├── backend/
│   ├── __init__.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── agents/
│   │   │   ├── assessor.py
│   │   │   └── coordinator.py
│   │   ├── api/
│   │   │   └── routes.py
│   │   ├── learner/
│   │   │   └── fake.py
│   │   ├── main.py
│   │   ├── policy/
│   │   │   └── fake.py
│   │   ├── storage/
│   │   │   └── memory.py
│   │   └── teaching/
│   │       ├── catalog.py
│   │       └── fake.py
│   ├── pyproject.toml
│   └── uv.lock
├── content/
│   └── demo.json
├── contracts/
│   ├── __init__.py
│   ├── api.ts
│   ├── fixtures/
│   │   └── turn_response.json
│   ├── interfaces.py
│   └── models.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── AWS.md
│   ├── CONTRACTS.md
│   ├── DEMO.md
│   ├── G1_REPORT.md
│   ├── OWNERSHIP.md
│   ├── PHASE2.md
│   └── WORKSTREAMS.md
├── frontend/
│   ├── index.html
│   ├── package-lock.json
│   ├── package.json
│   ├── src/
│   │   ├── main.tsx
│   │   └── style.css
│   ├── tsconfig.json
│   └── vite.config.ts
├── scripts/
│   ├── dev.py
│   ├── setup.sh
│   └── smoke.py
└── tests/
    └── integration/
        └── test_loop.py
```

## Files added

- `.gitignore`
- `Makefile`
- `backend/__init__.py`
- `backend/app/__init__.py`
- `backend/app/agents/assessor.py`
- `backend/app/agents/coordinator.py`
- `backend/app/api/routes.py`
- `backend/app/learner/fake.py`
- `backend/app/main.py`
- `backend/app/policy/fake.py`
- `backend/app/storage/memory.py`
- `backend/app/teaching/catalog.py`
- `backend/app/teaching/fake.py`
- `backend/pyproject.toml`
- `backend/uv.lock`
- `content/demo.json`
- `contracts/__init__.py`
- `contracts/api.ts`
- `contracts/fixtures/turn_response.json`
- `contracts/interfaces.py`
- `contracts/models.py`
- `docs/G1_REPORT.md`
- `frontend/index.html`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/src/main.tsx`
- `frontend/src/style.css`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `scripts/dev.py`
- `scripts/setup.sh`
- `scripts/smoke.py`
- `tests/integration/test_loop.py`

## Files modified

- `AGENTS.md`
- `CONTRIBUTING.md`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/CONTRACTS.md`
- `docs/PHASE2.md`
- `docs/WORKSTREAMS.md`
