# Learning workspace

The frontend uses the adaptive practice demo and the existing API contracts. Run `make dev` from the repository root, then open http://127.0.0.1:5173.

## Interaction design

- **Home:** a reference-inspired overview with a mint navigation rail, rounded shared surface, concept rows, local course goals, and a next-step action. The focus estimate and its 90% range come from the API. Unknown concepts say “No evidence yet”; there is no course-wide readiness score, streak, predicted learning gain, or generated study-time recommendation. Clicking a concept opens its evidence, and returning to Study desk preserves the selected answer and review state. The existing practice entry still opens Study desk directly.
- **Answer impact:** after each answer, “What changed?” compares the submitted question's concept using the retained `StudyEntry.before` and returned snapshots. It displays estimate, interval, interval width, observation count, exact intervention reason, and the next question or completion. Unchanged counts say “No new observation recorded” without inventing a cause. Showing teaching or changing preferences does not change the snapshots.
- **Teaching source:** `mode: dummy` / `provider: fake` supports “Deterministic teaching”; `tutor.fallback` supports “Marked fallback teaching.” The flag alone establishes neither human review nor a provider failure. Debug traces display the returned stage names rather than inferring implementation classes. Live teaching needs an agreed Tutor-specific provenance field; no shared contracts were changed.
- **Request authentication:** the API client reads the current existing Cognito ID token for each `sessions` request, including reset, and attaches its Bearer header. JSON payloads and token storage are unchanged. The current `/turns` route has no Authorization verification or session-ownership enforcement; turn authentication remains a backend integration dependency.
- **Chatbot:** a dedicated view reached from the left navigation, alongside Study desk, Concept map, and Session activity. On mobile the same navigation becomes a compact horizontal bar. The conversation contains submitted answer text and actual API-returned tutor explanations, with context disclosure, fallback labels, and the three existing teaching preferences. Suggested follow-ups fill an editable local draft; sending is explicitly unavailable because the current API has no chat endpoint. Drafts survive view changes and clear on successful session reset or sign-out. No fabricated replies, extra requests, file ingestion, or inference is performed.
- **Entry flow:** when configured, `#/login` links to Cognito Hosted UI using the existing Authorization Code + PKCE flow. Without frontend Cognito configuration it offers a clearly labeled local preview. Sign-out clears the local course draft and unmounts the study session. Rendering the hosted-login button or passing mocked header tests does not verify live authentication or backend session ownership.
- **Evidence review:** the recap compares public snapshots returned by the server, including uncertainty and evidence counts. The concept map shows submitted responses for the selected concept. Untouched concepts emphasize the absence of evidence.

- **Course setup:** the default screen (`#/setup`) is a single form with a navigable progress rail, optional file selection, goal/date/time controls, validation, and an editable review. File handles and setup details remain in tab memory and clear on refresh; no upload, document processing, or study-plan generation is implemented. The explicit practice-demo action opens the adaptive practice experience at `#/study`. Returning to setup preserves the draft and practice session.

- **Study desk:** answer → diagnosis and explanation → explicit next-question action → session recap. An unsubmitted selection survives revisiting the previous explanation.
- **Concept map:** inspect the six API-returned estimates. Connectors group topics, not prerequisites. Selecting a concept does not submit an answer or select a new activity.
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

- `npm --prefix frontend test`: nineteen component interaction tests, including Home navigation and evidence honesty, authenticated session/reset headers, before/after snapshots, unchanged evidence, concept inspection, full response flow, reset and preference isolation, pending/error recovery, keyboard interaction, onboarding, local-only materials, chatbot draft isolation, disabled sending, and marked fallback rendering. Tests use jsdom and mock the HTTP boundary with the shared response fixture; they are not browser layout tests.
- `npm --prefix frontend run build`: TypeScript check and production bundle.
- `make check` and `make smoke`: existing backend checks, frontend build, and real HTTP smoke.

The app remains a deterministic prototype. These automated checks do not certify visual layout, screen-reader behavior, or production service reliability.
