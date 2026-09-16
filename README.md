# Minds & Machines — deterministic learning lab

**G1 is implemented on `codex/baseline` and ready for review.** It is a local, two-question demo with four independently replaceable fakes. No real agents, model/provider calls, AWS integration, mathematical updates, policy scoring, authentication or persistence are implemented. G2 is not authorized.

## Run locally

Prerequisites: macOS/Linux, Python 3.12 or 3.13, Node.js 22.12+ (tested with Node 24), npm, and make. Windows users can use WSL; native Windows execution is not verified.

One-time dependency setup (requires package-registry access):

```sh
make setup
```

Uses an existing uv installation or installs pinned uv in ignored `.tools/`. Python dependencies are locked in `backend/uv.lock`; npm dependencies are locked in `frontend/package-lock.json`. No cloud keys are needed.

Start both frontend and FastAPI:

```sh
make dev
```

Open [the learning lab](http://127.0.0.1:5173). FastAPI listens on `127.0.0.1:8000`; Vite proxies `/api` to it. Ctrl-C stops both processes. Both ports must be free. Runtime works offline after setup. Sessions live only in backend memory; browser/backend restart requires a new session.

Run the small backend suite and frontend typecheck/build:

```sh
make check
```

Run the real HTTP core smoke, including reset and presentation-preference comparison:

```sh
make smoke
```

The smoke starts/stops its own server on an available loopback port. No separately running app is needed. It complements the browser walkthrough below; it does not mock API responses.

## Golden browser walkthrough

1. Start a new session. All six concepts show 50.0%, interval 5.0–95.0%, and zero evidence.
2. On the relationship question, choose **A: Every admissible heuristic is also consistent**, then **Check answer**.
3. See an incorrect diagnosis, a scripted **Worked example** and its reason, a tutor explanation, and `FakeAssessor → FakeLearner → FakePolicy → FakeTutor`. Only the relationship concept changes: mean `0.3333333333333333`, interval `[0.0253, 0.7764]`, evidence count 1.
4. On the fresh graph question, choose **B: Admissible, but not consistent**, then submit. The same concept becomes mean `0.5`, interval `[0.1354, 0.8646]`, count 2. The two-question demo completes. Other concepts never change.
5. Select **plain language / explain jargon**, **step-by-step**, and **concise**; click **New session / reset**. The initial question/state return and the checkboxes stay selected.
6. Repeat A then B. The first tutor response becomes short plain-language numbered steps. Assessment, estimates, intervals, evidence counts, intervention and next question match the first run. Changing a checkbox does not submit an answer or alter a prior response.

The screen rounds percentages to one decimal; the API returns the documented canned values. “I'm not sure yet” uses the single curated fallback without adding evidence. The golden sequence is the demonstrated state progression; other permitted answers have deterministic placeholder behavior and may leave estimates unchanged. This is intentionally not a learning model.

## Runtime boundaries

```text
React browser → POST /api/v1/turns → FastAPI route
  → Coordinator → FakeAssessor.assess
                → FakeLearner.update
                → FakePolicy.choose
                → FakeTutor.teach
  → API-owned in-memory state → public JSON → React
```

`backend/app/main.py` is the one composition root. All four interfaces are in `contracts/interfaces.py`; shared records are in `contracts/models.py`, the small frontend counterpart is `contracts/api.ts`, and the first golden response is in `contracts/fixtures/turn_response.json`. The replacement test substitutes each seam independently. Only FakeTutor receives presentation preferences. Completion also passes through FakeTutor with a null decision and a fixed message.

## Repository map

- `frontend/`: React screen, accessible controls and styles; no hard-coded API responses.
- `backend/app/api/`, `storage/`, `main.py`: request validation, in-memory state and wiring.
- `backend/app/agents/`: coordinator and FakeAssessor.
- `backend/app/learner/`, `policy/`, `teaching/`: the three other fakes and local content loader.
- `contracts/`: approved types/interfaces and example payload; no code generation.
- `content/demo.json`: six concept IDs, two questions and one teaching example in presentation variants.
- `tests/integration/test_loop.py`: five targeted tests, including all four seam replacements.
- `scripts/`: setup, dev process launcher, and real HTTP smoke.

Full relevant tree, files changed, verification and limitations: [G1 report](docs/G1_REPORT.md).

## Git and team status

Verified repository: [lukeeskinner/MindsAndMachines](https://github.com/lukeeskinner/MindsAndMachines). The user bootstrapped the empty remote with approved Phase 1 documentation at `5ecaecfdfa0484c8da18ceff9c6646a2b258f1ea`. The remote default is main. This implementation builds on that history on `codex/baseline`; main is not merged, rewritten or pushed by this task.

The technical checks and agent-run browser walkthrough are complete. Review by the five teammates and a teammate-run fresh checkout remain human acceptance steps; they are not claimed as completed. Do not start separate workstreams until team acceptance and any later explicitly authorized main merge.

Coding sessions begin with [AGENTS.md](AGENTS.md), then [Phase 2](docs/PHASE2.md), [contracts](docs/CONTRACTS.md), [ownership](docs/OWNERSHIP.md), [workstreams](docs/WORKSTREAMS.md), and [contributing](CONTRIBUTING.md). [Architecture](docs/ARCHITECTURE.md), [AWS strategy](docs/AWS.md), and [demo plan](docs/DEMO.md) preserve the larger product direction; they do not authorize G2 work.
