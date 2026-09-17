// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../src/App";
import fixture from "../../contracts/fixtures/turn_response.json";
import { AnswerImpact, teachingPreview } from "../src/components/study/AnswerImpact";
import type { StudyEntry } from "../src/components/study/model";
import type { TurnResponse } from "../../contracts/api";

const question = { ...fixture.next_question, question_id: "first", prompt: "Which relationship holds?" };
const initial = {session_id: fixture.session_id, question, concepts: fixture.session_start};
let fetchMock = vi.fn();
const respond = (body: unknown) => ({ok: true, json: async () => body});
beforeEach(() => {
  window.sessionStorage.clear();
  fetchMock = vi.fn().mockResolvedValueOnce(respond(initial));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const pct = (value: number) => `${(value * 100).toFixed(1)}%`;
async function answer(result: unknown = fixture, choice = "a") {
  fetchMock.mockResolvedValueOnce(respond(result));
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("radio", {name: question.choices.find(c => c.id === choice)!.text}));
  await user.click(screen.getByRole("button", {name: "Check answer", exact: true}));
  const impact = await screen.findByRole("region", {name: "What changed?"});
  return {user, impact, desk: screen.getByRole("tabpanel", {name: "Study desk"})};
}

it("shows a concise result, one prominent posterior, trusted estimate/count, and next action by default", async () => {
  const {impact, desk} = await answer();
  expect(within(desk).getByRole("heading", {name: "Not quite — let’s unpack it."})).toBeTruthy();
  expect(within(desk).getByText(teachingPreview(fixture.tutor.text))).toBeTruthy();
  expect(within(desk).getAllByRole("img")).toHaveLength(1);
  const current = fixture.concepts.find(c => c.concept_id === question.concept_id)!;
  expect(within(impact).getByRole("img").getAttribute("aria-label")).toBe(`Beta(${current.alpha}, ${current.beta}); mean ${pct(current.mean)}; 90% interval ${pct(current.interval90.lower)} to ${pct(current.interval90.upper)}; ${current.evidence_count} observations.`);
  expect(within(impact).getByText(pct(current.mean))).toBeTruthy();
  expect(within(impact).getByText("1 observation")).toBeTruthy();
  expect(within(impact).getByText("50.0% → 33.3%")).toBeTruthy();
  expect(within(impact).getByText("Uncertainty is still high.")).toBeTruthy();
  expect(within(desk).getByRole("heading", {name: "Next: Admissibility vs consistency"})).toBeTruthy();
  expect(within(desk).getByRole("button", {name: "Continue", exact: true})).toBeTruthy();
  expect(within(desk).queryByRole("table")).toBeNull();
  expect(within(desk).queryByText(fixture.decision.reason)).toBeNull();
  expect(within(desk).queryByText(fixture.next_question.prompt)).toBeNull();
  expect(within(desk).queryByRole("heading", {name: "Your understanding"})).toBeNull();
  expect(within(desk).getByRole("button", {name: "See model details"}).getAttribute("aria-expanded")).toBe("false");
});

it("opens all diagnostics with the keyboard, announces state, and never sends evidence on expand/collapse", async () => {
  const {user, desk} = await answer();
  const toggle = within(desk).getByRole("button", {name: "See model details"});
  toggle.focus();
  await user.keyboard("{Enter}");
  expect(toggle.getAttribute("aria-expanded")).toBe("true");
  expect(document.getElementById(toggle.getAttribute("aria-controls")!)).toBeTruthy();
  const details = within(desk).getByRole("region", {name: "Model comparison"});
  expect(within(details).getByRole("row", {name: "Beta parameters (α, β) 1, 1 1, 2"})).toBeTruthy();
  expect(within(details).getByRole("row", {name: "90% uncertainty range 5.0% – 95.0% 2.5% – 77.6%"})).toBeTruthy();
  expect(within(details).getByRole("row", {name: "Interval width 90.0 pp 75.1 pp"})).toBeTruthy();
  expect(within(details).getByText(fixture.decision.reason)).toBeTruthy();
  expect(within(details).getByText(fixture.assessment.feedback)).toBeTruthy();
  expect(within(details).getByText("Worked example")).toBeTruthy();
  expect(within(details).getByText(fixture.next_question.prompt)).toBeTruthy();
  expect(within(details).getByText(/New observation recorded/)).toBeTruthy();
  await user.keyboard(" ");
  expect(toggle.getAttribute("aria-expanded")).toBe("false");
  await waitFor(() => expect(within(desk).queryByRole("table")).toBeNull());
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

it.each(["correct", "unclear"] as const)("keeps the %s path grounded in returned snapshots", async outcome => {
  const concepts = outcome === "unclear" ? initial.concepts : fixture.concepts.map(c => c.concept_id === question.concept_id
    ? {...c, alpha: 2, beta: 1, mean: 2/3, evidence_count: 1, interval90: {lower: .2236, upper: .9747}} : c);
  const result = {...fixture, concepts, assessment: {...fixture.assessment, outcome, feedback: "Returned feedback."}};
  const {impact, desk} = await answer(result, outcome === "unclear" ? "unsure" : "b");
  expect(within(desk).getByRole("heading", {name: outcome === "correct" ? "Correct — nicely done." : "Not sure yet? Let’s work through it."})).toBeTruthy();
  expect(within(impact).getByText(outcome === "correct" ? "66.7%" : "50.0%")).toBeTruthy();
  expect(within(impact).getByText(outcome === "correct" ? "1 observation" : "0 observations")).toBeTruthy();
  if (outcome === "unclear") expect(within(impact).getByText(/No new observation recorded.*unchanged/)).toBeTruthy();
  expect(JSON.parse(fetchMock.mock.calls[1][1].body).answer).toBe(outcome === "unclear" ? "unsure" : "b");
});

it("continues to the actual remediation question without stale feedback or an open disclosure", async () => {
  const {user} = await answer();
  await user.click(screen.getByRole("button", {name: "See model details"}));
  await user.click(screen.getByRole("button", {name: "Continue", exact: true}));
  expect(screen.queryByRole("region", {name: "What changed?"})).toBeNull();
  expect(screen.queryByRole("button", {name: "See model details"})).toBeNull();
  expect(screen.getByRole("group", {name: fixture.next_question.prompt})).toBeTruthy();
  expect((screen.getByRole("button", {name: "Check answer"}) as HTMLButtonElement).disabled).toBe(true);
  fetchMock.mockResolvedValueOnce(respond({...fixture, assessment: {...fixture.assessment, outcome: "correct"}}));
  await user.click(screen.getByRole("radio", {name: fixture.next_question.choices[0].text}));
  await user.click(screen.getByRole("button", {name: "Check answer"}));
  await screen.findByRole("heading", {name: "Correct — nicely done."});
  expect(JSON.parse(fetchMock.mock.calls[2][1].body).question_id).toBe(fixture.next_question.question_id);
  expect(screen.getByRole("button", {name: "See model details"}).getAttribute("aria-expanded")).toBe("false");
});

it("labels review eligibility in the default next step without claiming fresh evidence", async () => {
  const {desk} = await answer({...fixture, next_question: {...fixture.next_question, review: true}});
  expect(within(desk).getByText("Review item: seen before. This answer will not add mastery evidence.")).toBeTruthy();
  expect(within(desk).queryByText("We still need more evidence on this concept.")).toBeNull();
});

it("does not invent uncertainty classifications or parameters missing from older responses", () => {
  const entry: StudyEntry = {question, answer: "a", before: [], result: {...fixture, analytics: undefined,
    concepts: [{concept_id: question.concept_id, mean: .42, evidence_count: 7, interval90: {lower:.2,upper:.7}}]} as TurnResponse};
  render(<AnswerImpact entry={entry} />);
  expect(screen.getByText("42.0%")).toBeTruthy();
  expect(screen.getByText("7 observations")).toBeTruthy();
  expect(screen.queryByText("Uncertainty is still high.")).toBeNull();
  expect(screen.queryByRole("img")).toBeNull();
});

it("excerpts complete teaching sentences without cutting decimals or changing returned prose", () => {
  const text = "Use 0.5 for x. Then apply f(x) = x². Check the result. A longer worked example follows.";
  expect(teachingPreview(text)).toBe("Use 0.5 for x. Then apply f(x) = x². Check the result.");
  expect(teachingPreview("Two short lines.\n\nTry a fresh example.")).toBe("Two short lines. Try a fresh example.");
});
