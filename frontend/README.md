# Learning workspace

The frontend uses the adaptive practice demo and the existing API contracts. Run `make dev` from the repository root, then open http://127.0.0.1:5173.

## Interaction design

- **Home:** a reference-inspired overview with a mint navigation rail, rounded shared surface, concept rows, local course goals, and a next-step action. The focus estimate and its 90% range come from the API. Unknown concepts say “No evidence yet”; there is no course-wide readiness score, streak, predicted learning gain, or generated study-time recommendation. Clicking a concept opens its evidence, and returning to Study desk preserves the selected answer and review state. The existing practice entry still opens Study desk directly.
- **Answer impact:** after each answer, “What changed?” compares the submitted question's concept using the retained `StudyEntry.before` and returned snapshots. It displays estimate, interval, interval width, observation count, exact intervention reason, and the next question or completion. Unchanged counts say “No new observation recorded” without inventing a cause. Showing teaching or changing preferences does not change the snapshots.
- **Teaching source:** preserves the public `tutor.teaching_source` labels: Authored teaching, AI-generated teaching, and Reviewed fallback. Missing or contradictory provenance stays explicitly unreported/marked fallback; provider names and prose never establish generation.

- **Request authentication:** the API client reads the current existing Cognito ID token for each `sessions` request, including reset, and attaches its Bearer header. Demo payloads and token storage are unchanged; uploaded-course creation adds the shared optional `course_id`. The current `/turns` route has no Authorization verification or session-ownership enforcement; turn authentication remains a backend integration dependency.
- **Chatbot:** a dedicated view reached from the left navigation, alongside Study desk, Concept map, and Session activity. On mobile the same navigation becomes a compact horizontal bar. The conversation contains submitted answer text and actual API-returned tutor explanations, with context disclosure, fallback labels, and the three existing teaching preferences. Suggested follow-ups fill an editable local draft; sending is explicitly unavailable because the current API has no chat endpoint. Drafts survive view changes and clear on successful session reset or sign-out. No fabricated replies, extra requests, file ingestion, or inference is performed.
- **Entry flow:** when configured, `#/login` links to Cognito Hosted UI using the existing Authorization Code + PKCE flow. Without frontend Cognito configuration it offers a clearly labeled local preview. Sign-out clears the local course draft and unmounts the study session. Rendering the hosted-login button or passing mocked header tests does not verify live authentication or backend session ownership.
- **Evidence review:** the recap compares public snapshots returned by the server, including uncertainty and evidence counts. The concept map shows submitted responses for the selected concept. Untouched concepts emphasize the absence of evidence.

- **Course setup:** the default screen (`#/setup`) is a single form with a navigable progress rail, optional file selection, goal/date/time controls, validation, and an editable review. File handles and setup details remain in tab memory and clear on refresh; upload sends the selected materials to the course service; no document processing or study-plan generation runs in the browser. The explicit practice-demo action opens the adaptive practice experience at `#/study`. Returning to setup preserves the draft and practice session.

- **Study desk:** answer → diagnosis and explanation → explicit next-question action → session recap. An unsubmitted selection survives revisiting the previous explanation.
- **Concept map:** inspect the active course’s API-returned estimates. Connectors group topics, not prerequisites. Selecting a concept does not submit an answer or select a new activity.
- **Session activity:** review submitted choices, tutor text, and the actual returned stage trace. This journal lives in browser memory and clears on reset.
- **Inspector:** compact concept details remain beside practice. Explanation preferences are shared between the inspector and Chatbot, affect the next request only, and survive reset.

All knowledge values, questions, grading, and activity choices come from the backend. No frontend inference, new endpoints, shared contract changes, or live providers were added. The interface labels the deterministic mode and experimental estimates.

## Components and styling

`src/App.tsx` owns session presentation state. `src/lib/api.ts` sends the existing POST requests. The components in `src/components/ui/` are customized shadcn/ui registry components, retaining Radix keyboard and ARIA behavior. `primitives.tsx` composes those components with Motion for panels and disclosures. `components.json` configures further shadcn additions.

Tailwind CSS v4 runs through the Vite plugin. The visual system is defined in `src/style.css` using semantic `@theme` tokens, utility recipes, and layout rules in the components layer. It uses the requested exact teal, sky, yellow, orange, green, coral, slate, and white palette. Teal controls selection and actions; sky distinguishes topic grouping and decision context; yellow marks the deterministic mode/uncertainty; orange marks incorrect feedback; green marks successful feedback; coral marks errors. Accent colors supplement text and icons rather than encoding meaning alone.

Manrope headings and DM Sans body text are bundled locally. Motion handles view entrances, expanding/collapsing disclosures, and server-returned estimate changes. Both Motion and CSS respect reduced-motion preferences. The layout keeps a single study surface and an open, compact inspector rather than a grid of cards.

### Component provenance

Button, tabs, switch, collapsible, input, and native-select source was retrieved from the official [shadcn/ui registry](https://ui.shadcn.com/r/styles/new-york-v4/button.json) on 2026-09-16. Recipes are customized for this workspace, imports use the existing per-component Radix packages, and `cn` is local. The upstream [MIT license](licenses/shadcn-ui-LICENSE.md) is retained.

## Checks

- `npm --prefix frontend test`: component interaction tests, including Home navigation and evidence honesty, authenticated session/reset headers, before/after snapshots, unchanged evidence, concept inspection, full response flow, reset and preference isolation, pending/error recovery, keyboard interaction, onboarding, local-only materials, chatbot draft isolation, disabled sending, and marked fallback rendering. Tests use jsdom and mock the HTTP boundary with the shared response fixture; they are not browser layout tests.
- `npm --prefix frontend run build`: TypeScript check and production bundle.
- `make check` and `make smoke`: existing backend checks, frontend build, and real HTTP smoke.

The app remains a deterministic prototype. These automated checks do not certify visual layout, screen-reader behavior, or production service reliability.

## Uploaded-course frontend integration

This workstream changes only `frontend/`. Shared `contracts/api.ts` and all backend
modules are unchanged. The active public course is separate from the editable
local setup draft. Only PDF and PPTX are selectable (local limits: eight files,
20 MB each). Goals remain local and are not sent in session or turn requests.

The default `CourseProvider` uses the real upload adapter; `RootApp` still accepts
an optional `courseAdapter` override for tests. Upload starts only on the learner’s
explicit action. There are no production mocks, inferred completion, progress
timers, polling requests or job IDs.

The adapter in `src/lib/courses.ts` uses the confirmed backend contract:

- `POST /api/v1/courses`, multipart `files` (one or more PDF/PPTX files), with
  optional `title`. Blank/omitted titles are not sent. The browser sets the
  multipart boundary. Processing occurs within this one request.
- The UI announces “Uploading and processing” while awaiting the response and
  disables duplicate upload/file edits. Only HTTP 201 with validated existing
  `PublicCourse` metadata enters ready state. There is no separate status endpoint.
- HTTP failures map to safe messages; raw error bodies are never displayed.
  HTTP 400 gives file-count/format/size guidance without guessing from free-text
  exceptions; 413 covers size, 415 format, 422 processing/extraction, and other
  service/provider/network failures allow retry. Local selection also enforces
  the file-count and size limits. Unexpected 200/202 responses cannot activate a
  course. The endpoint is expected to be mounted during final integration.
- The metadata projection copies only title, ID, concept IDs/display names,
  source filenames and question count. Private extras are not kept or rendered.
- Session creation and reset use the existing `/sessions`: selected uploads send
  `{course_id}`; demo sends `{}`. Existing session auth handling is preserved.
  The echoed course ID and all returned concept IDs must match. Course switches
  unmount the old session UI so old questions, answers, evidence, chat drafts and
  late responses cannot appear in the new course. Reset retains preferences and
  the selected course; returning to demo is an explicit action in Materials.
- Uploaded-course runtime still needs backend activation. The frontend renders
  the existing public question/turn records and Bayesian snapshots without
  computing estimates or inventing teaching. A 409 explains that course study is
  not enabled. A missing course (404) explains restart/re-upload recovery and
  never silently falls back to demo. Server exception strings are not displayed.
- `QuestionSource` is a compact, optional filename/page/slide presentation seam.
  It is intentionally not fed from course filenames (which do not establish a
  question citation) or private evidence. Wire it into question rendering only
  after the backend publishes explicit public question-level provenance. No
  shared provenance contract or fabricated citation was added.

`CourseContext` holds only frontend selection/upload presentation state. Backend
session/learner state remains API-owned. Setup and workspace share upload status;
refresh/sign-out clears local selection. Metadata-driven labels apply to Study
desk, Home, Concept map, evidence, Chatbot, and course navigation. Demo names and
groups are used only without an uploaded course. Keyboard controls, live status,
error alerts, focus styles and reduced-motion rules remain in place.

`tests/courses.test.tsx` mocks the adapter and HTTP boundary for upload/runtime
integration. It covers PDF/PPTX validation, uploading/processing/
ready/failure, safe metadata, course activation, course/response isolation,
reset/restart, dynamic labels, Bayesian display, teaching provenance, keyboard
upload activation and the optional public source component. These tests do not claim
that live ingestion or uploaded-course teaching works on this backend.
