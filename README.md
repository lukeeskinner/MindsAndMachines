# Minds & Machines — adaptive learning lab

**G2 assessor runtime integration:** the adaptive demo uses RealAssessor, BayesianLearner, AdaptivePolicy and the existing Tutor. Answer-key grading is authoritative. Local assessment and teaching are deterministic; explicit Bedrock configuration enables bounded diagnosis and validated teaching prose with reviewed fallback. This scoped increment does not authorize deployment or further G2 work.

**Uploaded-course integration:** PDF/PPTX uploads can now start course-bound learning sessions through those same seams, using course-specific questions and stored teaching. Concept progression continues until the uploaded study bank is exhausted. See the [integration handoff and manual Grad Algorithms walkthrough](docs/UPLOADED_COURSE_INTEGRATION.md).

## Run locally

The study desk includes **Practice quiz** and **Flashcards**. The demo has eight
questions and eight study cards. New uploads contain 5–10 questions across up to
five source concepts, with source-backed concept summaries as flashcards. Bedrock
plans vary the count with material breadth; local mode uses source-recall and
masked-source exercises. Previously stored courses retain their bank size until
reprocessed.

Flashcards support answer reveal, previous/next arrows, topic filtering, and
**Got it / Review again**. Browsing does not mark a card reviewed. After a pass,
repeat the cards marked again or restart the deck. Switching views preserves the
quiz answer and deck position; reset clears both. Flashcards never add assessment
evidence or invoke the provider.

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

The browser starts at a frontend-only Amazon Cognito sign-in gate before course setup. Without Cognito env vars it creates a local `sessionStorage` preview session and does not call the backend. To show a real hosted sign-in link, set `VITE_COGNITO_DOMAIN`, `VITE_COGNITO_CLIENT_ID`, and optionally `VITE_COGNITO_REDIRECT_URI`; API contracts and FastAPI state remain unchanged.

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
3. See an incorrect diagnosis, a **Socratic hint** and its selection reason, and guidance labeled **Authored teaching** in default local mode. Only the relationship concept changes: mean `0.3333333333333333`, interval `[0.0253, 0.7764]`, evidence count 1.
4. On the graph with h(S)=6 and h(A)=4, choose **A: Both admissible and consistent**, then submit. The same concept becomes mean `0.5`, interval `[0.1354, 0.8646]`, count 2. A **Diagnostic probe** introduces a fresh graph.
5. On the graph with h(S)=5 and h(A)=1, choose **A: Admissible, but not consistent**. A **Worked example** introduces the original transfer question. Choose **B: Admissible, but not consistent**, then answer the four additional transfer/reasoning questions C, B, C, B to complete the eight-question demo. The relationship concept now has eight observations; other concepts never change.
6. Select **plain language / explain jargon**, **step-by-step**, and **concise**; click **New session / reset**. The initial question/state return and the checkboxes stay selected.
7. Repeat A, A, A, B, C, B, C, B. Teaching becomes short plain-language numbered steps. Assessment, estimates, intervals, evidence counts, interventions and next questions match the first run. Changing a checkbox does not submit an answer or alter a prior response.

The screen rounds percentages to one decimal; the API returns Bayesian estimates. “I'm not sure yet” uses reviewed fallback without adding evidence. Teaching alone never increases an estimate.

## Manual live assessment and Tutor test

From a developer shell with the workshop's temporary AWS credentials already exported:

```sh
MODEL_PROVIDER=bedrock AWS_REGION=us-east-1 BEDROCK_MODEL_ID=amazon.nova-lite-v1:0 BEDROCK_TIMEOUT_SECONDS=12 make dev
```

Open [the learning lab](http://127.0.0.1:5173) and follow the first-answer walkthrough. Accepted Bedrock prose shows **AI-generated teaching**; provider timeout/error or rejected output shows **Reviewed fallback**, with the same policy-selected next question. Completion is authored even in Bedrock mode. `MODEL_PROVIDER=fake` (the default) or `local` never invokes the provider through Assessment or Tutor. Selected files remain local until **Upload course**; uploaded content is processed by the backend, and course Tutor personalization receives the selected artifact's display-safe grounding.

Each turn caps assessment provider work at 4 seconds and Tutor provider work at 12 seconds, within an 18-second coordinator deadline. The browser keeps its 20-second request timeout. `BEDROCK_TIMEOUT_SECONDS` defaults to 12 and accepts values above zero up to 15; each interactive call uses the smallest configured, stage and remaining turn budget. The two sequential provider waits total at most 16 seconds, reserving 2 seconds for local turn work and 2 seconds for HTTP overhead. If the total coordinator deadline expires, the API returns a controlled 504 before saving the turn. This bounds asynchronous turn work, not external storage/network delays or synchronous event-loop stalls. A timed-out SDK thread can finish later, but its result is ignored and cannot update the session. SDK socket deadlines are also set and retries are disabled. No provider switching or whole-turn retries occur. Do not store credentials in repository files. `make check` and `make smoke` use mocked/local providers and do not test live AWS access.

Course generation is a larger, separate upload request. Its single provider call
uses `BEDROCK_INGESTION_TIMEOUT_SECONDS`, default 60 seconds, allowed above zero up
to 90. The upload browser timeout stays 120 seconds. This does not extend tutoring
deadlines or add retries. The provider attempt log includes
`timeout_seconds='60' purpose=course_ingestion` with the default configuration.

For a live failure diagnosis, stop the existing dev launcher with Ctrl-C and run
the command above again (the backend does not hot-reload). The backend terminal
logs `runtime_start` with PID and provider/model configuration, `provider_attempt`,
`bedrock_converse_started`, `bedrock_response_received` with an allowlisted stop
reason, and `provider_returned` on success. `provider_failed` distinguishes timeout,
configuration, missing credentials and allowlisted AWS error codes. `tutor_result`
reports whether the provider was attempted, the final teaching source and an
accepted/local/provider/JSON/validation reason. A validation rejection also logs
an allowlisted rule description. These logs omit credentials, headers, raw
exceptions, prompts and generated text. Share only these diagnostic lines.
The public `dummy/fake` values describe authored fallback, so they alone cannot
establish whether a Bedrock attempt occurred.

If course upload returns a validation failure, the backend now logs
`course_ingestion_failed reason=...` with a fixed diagnostic code, such as
`malformed_generated_json`, `answer_source_mismatch`, or `teaching_answer_leakage`.
Unknown errors log `unclassified_validation`; exception text, extracted material
and provider output are never included. Restart the dev launcher after backend
edits, retry once, and use this code to diagnose the rejected rule before changing
validation. A generic upload error alone does not establish that the PDF is bad.

## Runtime boundaries

```text
React browser → POST /api/v1/turns → FastAPI route
  → Coordinator → RealAssessor.assess
                → BayesianLearner.update
                → AdaptivePolicy.choose
                → Tutor.teach (authored or validated Bedrock)
  → API-owned in-memory state → public JSON → React
```

`backend/app/main.py` is the one composition root. All four interfaces are in `contracts/interfaces.py`; shared records are in `contracts/models.py`, the small frontend counterpart is `contracts/api.ts`, and the first golden response is in `contracts/fixtures/turn_response.json`. The replacement test substitutes each seam independently. Only Teaching receives presentation preferences. Completion passes through Tutor with a null decision and a fixed message. FakeAssessor remains available for unit tests; FakeTutor remains available for tests and authored rendering. Assessment failure retains answer-key evidence and deterministic feedback, and Tutor can continue. Reviewed misconception signals apply only to q01/a, q02/a and q03/b; q04 and unknown question IDs receive no diagnosis. See [assessor runtime notes](backend/app/agents/REAL_ASSESSOR.md) for the educational rationale and deadline behavior.

## Repository map

- `frontend/`: React screen, accessible controls and styles; no hard-coded API responses.
- `backend/app/api/`, `storage/`, `main.py`: request validation, in-memory state and wiring.
- `backend/app/agents/`: coordinator, RealAssessor, provider adapter and test fake.
- `backend/app/learner/`, `policy/`, `teaching/`: real implementations, replaceable fakes and local content loader.
- `contracts/`: approved types/interfaces and example payload; no code generation.
- `content/demo.json`: six concept IDs, eight questions and three authored teaching approaches in presentation variants.
- `tests/integration/`: golden loop, seam replacements and mocked Bedrock runtime/failure tests.
- `scripts/`: setup, dev process launcher, and real HTTP smoke.

Full relevant tree, files changed, verification and limitations: [G1 report](docs/G1_REPORT.md).

## Historical G1 handoff

Verified repository: [lukeeskinner/MindsAndMachines](https://github.com/lukeeskinner/MindsAndMachines). The user bootstrapped the empty remote with approved Phase 1 documentation at `5ecaecfdfa0484c8da18ceff9c6646a2b258f1ea`. The remote default is main. This implementation builds on that history on `codex/baseline`; main is not merged, rewritten or pushed by this task.

The technical checks and agent-run browser walkthrough are complete. Review by the five teammates and a teammate-run fresh checkout remain human acceptance steps; they are not claimed as completed. Do not start separate workstreams until team acceptance and any later explicitly authorized main merge.

Coding sessions begin with [AGENTS.md](AGENTS.md), then [Phase 2](docs/PHASE2.md), [contracts](docs/CONTRACTS.md), [ownership](docs/OWNERSHIP.md), [workstreams](docs/WORKSTREAMS.md), and [contributing](CONTRIBUTING.md). [Architecture](docs/ARCHITECTURE.md), [AWS strategy](docs/AWS.md), and [demo plan](docs/DEMO.md) preserve the larger product direction; they do not authorize G2 work.
