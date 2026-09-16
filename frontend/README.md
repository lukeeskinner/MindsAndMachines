# Learning workspace

The frontend branch redesign retains the two-question G1 demo and the existing API contracts. Run `make dev` from the repository root, then open http://127.0.0.1:5173.

## Interaction design

- **Course setup:** the default screen (`#/setup`) is a single form with a navigable progress rail, optional file selection, goal/date/time controls, validation, and an editable review. File handles and setup details remain in tab memory and clear on refresh; no upload, document processing, or study-plan generation is implemented. The explicit practice-demo action opens the existing two-question experience at `#/study`. Returning to setup preserves the draft and practice session.

- **Study desk:** answer → diagnosis and explanation → explicit next-question action → session recap. An unsubmitted selection survives revisiting the previous explanation.
- **Concept map:** inspect the six API-returned estimates. Connectors group topics, not prerequisites. Selecting a concept does not submit an answer or select a new activity.
- **Session activity:** review submitted choices, tutor text, and the actual returned stage trace. This journal lives in browser memory and clears on reset.
- **Inspector:** compact concept rows, one selected uncertainty interval, and learner-controlled teaching preferences. Preferences affect the next request only and survive reset.

All knowledge values, questions, grading, and activity choices come from the backend. No frontend inference, new endpoints, shared contract changes, or live providers were added. The interface labels the deterministic mode and experimental estimates.

## Components and styling

`src/App.tsx` owns session presentation state. `src/lib/api.ts` sends the existing POST requests. The components in `src/components/ui/` are customized shadcn/ui registry components, retaining Radix keyboard and ARIA behavior. `primitives.tsx` composes those components with Motion for panels and disclosures. `components.json` configures further shadcn additions.

Tailwind CSS v4 runs through the Vite plugin. The visual system is defined in `src/style.css` using semantic `@theme` tokens, utility recipes, and layout rules in the components layer. It uses the requested exact teal, sky, yellow, orange, green, coral, slate, and white palette. Teal controls selection and actions; sky distinguishes topic grouping and decision context; yellow marks the deterministic mode/uncertainty; orange marks incorrect feedback; green marks successful feedback; coral marks errors. Accent colors supplement text and icons rather than encoding meaning alone.

Manrope headings and DM Sans body text are bundled locally. Motion handles view entrances, expanding/collapsing disclosures, and server-returned estimate changes. Both Motion and CSS respect reduced-motion preferences. The layout keeps a single study surface and an open, compact inspector rather than a grid of cards.

### Component provenance

Button, tabs, switch, collapsible, input, and native-select source was retrieved from the official [shadcn/ui registry](https://ui.shadcn.com/r/styles/new-york-v4/button.json) on 2026-09-16. Recipes are customized for this workspace, imports use the existing per-component Radix packages, and `cn` is local. The upstream [MIT license](licenses/shadcn-ui-LICENSE.md) is retained.

## Checks

- `npm --prefix frontend test`: nine component interaction tests covering the full response flow, request payloads, concept exploration, reset and preference isolation, pending/error recovery, keyboard interaction, onboarding validation, file selection/removal, and setup-to-study navigation. Tests use jsdom and mock the HTTP boundary with the shared response fixture; they are not browser layout tests.
- `npm --prefix frontend run build`: TypeScript check and production bundle.
- `make check` and `make smoke`: existing backend checks, frontend build, and real HTTP smoke.

The app remains a deterministic prototype. These automated checks do not certify visual layout, screen-reader behavior, or production service reliability.
