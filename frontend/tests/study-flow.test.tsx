// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../src/App";
import fixture from "../../contracts/fixtures/turn_response.json";

const firstQuestion = {
  question_id: "relationship-q01",
  concept_id: "admissibility_vs_consistency",
  prompt: "Which relationship is true?",
  choices: [
    { id: "a", text: "Every admissible heuristic is also consistent." },
    { id: "b", text: "Every consistent heuristic is admissible." },
    { id: "unsure", text: "I'm not sure yet." },
  ],
};
const initial = {
  session_id: "example-session",
  question: firstQuestion,
  concepts: fixture.concepts.map((c) => ({
    ...c,
    mean: 0.5,
    interval90: { lower: 0.05, upper: 0.95 },
    evidence_count: 0,
  })),
};
const completed = {
  ...fixture,
  assessment: {
    outcome: "correct",
    misconception_id: null,
    feedback: "You checked both conditions.",
  },
  concepts: fixture.concepts.map((c) =>
    c.concept_id === "admissibility_vs_consistency"
      ? {
          ...c,
          mean: 0.5,
          interval90: { lower: 0.1354, upper: 0.8646 },
          evidence_count: 2,
        }
      : c,
  ),
  decision: null,
  tutor: { text: "Two-question demo complete.", fallback: false },
  next_question: null,
};
const respond = (body: unknown, ok = true) => ({ ok, json: async () => body });
let fetchMock = vi.fn();
beforeEach(() => {
  window.sessionStorage.clear();
  fetchMock = vi.fn().mockResolvedValueOnce(respond(initial));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
});
async function start() {
  const user = userEvent.setup();
  render(<App />);
  await screen.findByRole("radio", { name: firstQuestion.choices[0].text });
  return user;
}

describe("study desk interactions", () => {
  it("keeps the real request shape, stages feedback before the next question, and completes the loop", async () => {
    fetchMock
      .mockResolvedValueOnce(respond(fixture))
      .mockResolvedValueOnce(respond(completed));
    const user = await start();
    expect(
      (
        screen.getByRole("button", {
          name: "Check answer",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    await user.click(screen.getByRole("switch", { name: /Plain language/ }));
    await user.click(
      screen.getByRole("radio", { name: firstQuestion.choices[0].text }),
    );
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    await screen.findByRole("heading", {
      name: "Here’s the useful distinction.",
    });
    expect(fetchMock.mock.calls[1][0]).toBe("/api/v1/turns");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      session_id: "example-session",
      question_id: "relationship-q01",
      answer: "a",
      presentation_preferences: {
        plain_language: true,
        step_by_step: false,
        concise: false,
      },
    });
    expect(screen.queryByRole("radio")).toBeNull();
    expect(
      screen.getByRole("button", {
        name: /Admissibility vs consistency.*33.3%/,
      }),
    ).toBeTruthy();
    expect(screen.getByText("2.5%–77.6%")).toBeTruthy();
    await user.click(
      screen.getByRole("button", { name: "Behind this response" }),
    );
    expect(screen.getByText("update")).toBeTruthy();
    expect(screen.getByText("select")).toBeTruthy();
    expect(screen.queryByText("FakeLearner")).toBeNull();
    expect(screen.queryByText("FakePolicy")).toBeNull();
    await user.click(
      screen.getByRole("button", { name: "Try the next question" }),
    );
    await user.click(
      screen.getByRole("radio", { name: "Admissible, but not consistent." }),
    );
    await user.click(
      screen.getByRole("button", { name: "Revisit the explanation" }),
    );
    await user.click(
      screen.getByRole("button", { name: "Try the next question" }),
    );
    expect(
      (
        screen.getByRole("radio", {
          name: "Admissible, but not consistent.",
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    await screen.findByRole("button", { name: "Session recap" });
    await user.click(screen.getByRole("button", { name: "Session recap" }));
    expect(
      screen.getByRole("heading", { name: "A connection worth keeping." }),
    ).toBeTruthy();
    const changes = screen.getByRole("region", {
      name: "Returned concept changes",
    });
    expect(changes.textContent).toContain("Observations: 0 → 2");
    expect(changes.textContent).toContain("5.0%–95.0% → 13.5%–86.5%");
    await user.click(screen.getByRole("tab", { name: "Session activity" }));
    expect(
      screen.getByRole("heading", { name: "The relationship" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "A fresh example" }),
    ).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("lets learners explore concepts without grading, and resets evidence while preserving preferences", async () => {
    fetchMock
      .mockResolvedValueOnce(respond(fixture))
      .mockResolvedValueOnce(
        respond({ ...initial, session_id: "fresh-session" }),
      );
    const user = await start();
    await user.click(screen.getByRole("switch", { name: /Step by step/ }));
    await user.click(
      screen.getByRole("radio", { name: firstQuestion.choices[0].text }),
    );
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    await screen.findByRole("button", { name: "Try the next question" });
    await user.click(screen.getByRole("tab", { name: "Concept map" }));
    const map = screen.getByRole("tabpanel", { name: "Concept map" });
    await user.click(within(map).getByRole("button", { name: /BFS/ }));
    expect(
      within(map).getByRole("heading", { name: "Breadth-first search" }),
    ).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await user.click(
      screen.getByRole("button", { name: "New session / reset" }),
    );
    await screen.findByRole("radio", { name: firstQuestion.choices[0].text });
    expect(
      screen
        .getByRole("switch", { name: /Step by step/ })
        .getAttribute("aria-checked"),
    ).toBe("true");
    expect(
      screen.getByRole("button", {
        name: /Admissibility vs consistency.*No evidence/,
      }),
    ).toBeTruthy();
    expect(screen.getByText("0 observations")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Session activity" }));
    expect(
      screen.getByRole("heading", { name: "Your thinking starts here." }),
    ).toBeTruthy();
  });

  it("disables duplicate submissions while pending and offers reset after a request failure", async () => {
    let release!: (value: unknown) => void;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    );
    fetchMock.mockResolvedValueOnce(respond(initial));
    const user = await start();
    await user.click(
      screen.getByRole("radio", { name: firstQuestion.choices[0].text }),
    );
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    const pendingButton = screen.getByRole("button", {
      name: "Checking answer",
    });
    expect((pendingButton as HTMLButtonElement).disabled).toBe(true);
    await user.click(pendingButton);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    release(respond({ detail: "Session expired." }, false));
    await screen.findByRole("alert");
    expect(
      (
        screen.getByRole("button", {
          name: "Check answer",
        }) as HTMLButtonElement
      ).disabled,
    ).toBe(true);
    await user.click(screen.getByRole("button", { name: "Try new session" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(
      (
        screen.getByRole("radio", {
          name: firstQuestion.choices[0].text,
        }) as HTMLInputElement
      ).disabled,
    ).toBe(false);
  });

  it("supports keyboard answers, tab navigation, and preference switches", async () => {
    const user = await start();
    screen.getByRole("radio", { name: firstQuestion.choices[0].text }).focus();
    await user.keyboard(" ");
    await user.keyboard("{ArrowDown}");
    expect(
      (
        screen.getByRole("radio", {
          name: firstQuestion.choices[1].text,
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    const preference = screen.getByRole("switch", { name: /Keep it concise/ });
    preference.focus();
    await user.keyboard(" ");
    expect(preference.getAttribute("aria-checked")).toBe("true");
    screen.getByRole("tab", { name: "Study desk" }).focus();
    await user.keyboard("{ArrowDown}");
    await screen.findByRole("tabpanel", { name: "Chatbot" });
    await user.keyboard("{ArrowDown}");
    await screen.findByRole("tabpanel", { name: "Concept map" });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("keeps chatbot drafts local across views and clears them on successful reset", async () => {
    fetchMock.mockResolvedValueOnce(
      respond({ ...initial, session_id: "fresh-session" }),
    );
    const user = await start();
    const navigation = screen.getByRole("tablist", {
      name: "Learning workspace",
    });
    await user.click(within(navigation).getByRole("tab", { name: "Chatbot" }));
    const draft = screen.getByRole("textbox", {
      name: "Your follow-up draft",
    }) as HTMLTextAreaElement;
    await user.click(
      screen.getByRole("button", { name: "Walk me through the example" }),
    );
    expect(draft.value).toBe("Walk me through the example");
    expect(document.activeElement).toBe(draft);
    await user.type(draft, " with smaller steps.");
    await user.keyboard("{Enter}");
    const send = screen.getByRole("button", {
      name: "Send",
    }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
    await user.click(send);
    await user.click(screen.getByRole("tab", { name: "Study desk" }));
    expect(
      screen.queryByRole("textbox", { name: "Your follow-up draft" }),
    ).toBeNull();
    await user.click(screen.getByRole("tab", { name: "Chatbot" }));
    await user.click(screen.getByRole("tab", { name: "Concept map" }));
    expect(draft.value).toContain("with smaller steps.");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    await user.click(
      screen.getByRole("button", { name: "New session / reset" }),
    );
    await screen.findByRole("radio", { name: firstQuestion.choices[0].text });
    await user.click(screen.getByRole("tab", { name: "Chatbot" }));
    await waitFor(() =>
      expect(
        (
          screen.getByRole("textbox", {
            name: "Your follow-up draft",
          }) as HTMLTextAreaElement
        ).value,
      ).toBe(""),
    );
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("renders only returned explanations, preserves unsure evidence, and exposes public context", async () => {
    const unsure = {
      ...fixture,
      concepts: initial.concepts,
      assessment: {
        outcome: "unclear",
        misconception_id: null,
        feedback: "No evidence applied.",
      },
      tutor: {
        text: "A returned fallback explanation.\n\n<script>not executable</script>",
        fallback: true,
      },
    };
    fetchMock.mockResolvedValueOnce(respond(unsure));
    const user = await start();
    await user.click(screen.getByRole("radio", { name: "I'm not sure yet." }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    await screen.findByRole("button", { name: "Read explanation" });
    await user.click(screen.getByRole("button", { name: "Read explanation" }));
    await screen.findByRole("tabpanel", { name: "Chatbot" });
    const conversation = screen.getByRole("region", {
      name: "Study conversation",
    });
    expect(
      within(conversation).getByText("A returned fallback explanation."),
    ).toBeTruthy();
    expect(
      within(conversation).getByText("Marked fallback teaching"),
    ).toBeTruthy();
    expect(
      within(conversation).getByText("<script>not executable</script>"),
    ).toBeTruthy();
    expect(conversation.querySelector("script")).toBeNull();
    await user.click(
      screen.getByRole("button", { name: "Context for this conversation" }),
    );
    expect(screen.getByText(fixture.next_question.prompt)).toBeTruthy();
    expect(screen.getByText(/0 observations · 50.0% estimate/)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await user.click(screen.getByRole("tab", { name: "Concept map" }));
    const responses = screen.getByRole("region", {
      name: "Answers for this concept",
    });
    expect(within(responses).getByText("No evidence applied.")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("adaptive evidence and trust", () => {
  it("keeps Home grounded in returned evidence and preserves a selected practice answer", async () => {
    const user = await start();
    await user.click(
      screen.getByRole("radio", { name: firstQuestion.choices[0].text }),
    );
    await user.click(screen.getByRole("tab", { name: "Home", exact: true }));
    const home = screen.getByRole("region", { name: "Learning overview" });
    expect(within(home).getByText("50.0%")).toBeTruthy();
    expect(within(home).getByText("5.0% – 95.0%")).toBeTruthy();
    expect(
      within(home).getByText("Starting estimate · no evidence yet"),
    ).toBeTruthy();
    expect(within(home).getByText("No date set")).toBeTruthy();
    expect(
      within(home).getByText(/Files and goals are not supplied to the tutor/),
    ).toBeTruthy();
    expect(home.textContent).not.toMatch(
      /exam readiness|streak|expected.*gain|recommended study time/i,
    );
    await user.click(
      within(home).getByRole("button", {
        name: /Breadth-first search/,
      }),
    );
    expect(
      screen.getByRole("region", { name: "Selected concept evidence" })
        .textContent,
    ).toContain("Breadth-first search");
    await user.click(screen.getByRole("tab", { name: "Home", exact: true }));
    await user.click(screen.getByRole("button", { name: "Start studying" }));
    expect(
      (
        screen.getByRole("radio", {
          name: firstQuestion.choices[0].text,
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows the returned strategy on Home and carries the learner back to the answer review", async () => {
    fetchMock.mockResolvedValueOnce(respond(fixture));
    const user = await start();
    await user.click(
      screen.getByRole("radio", { name: firstQuestion.choices[0].text }),
    );
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    await screen.findByRole("region", { name: "What changed?" });
    await user.click(screen.getByRole("tab", { name: "Home", exact: true }));
    const home = screen.getByRole("region", { name: "Learning overview" });
    expect(within(home).getByText("1 observation recorded")).toBeTruthy();
    expect(
      within(home).getByRole("heading", { name: "Worked example" }),
    ).toBeTruthy();
    expect(within(home).getByText("Deterministic teaching")).toBeTruthy();
    const why = within(home).getByRole("button", { name: "Why this next?" });
    why.focus();
    await user.keyboard("{Enter}");
    expect(within(home).getByText(fixture.decision.reason)).toBeTruthy();
    await user.click(
      within(home).getByRole("button", { name: "Continue learning" }),
    );
    expect(screen.getByRole("region", { name: "What changed?" })).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("compares returned snapshots after each answer and shows the actual reason and next question", async () => {
    fetchMock
      .mockResolvedValueOnce(respond(fixture))
      .mockResolvedValueOnce(respond(completed));
    const user = await start();
    await user.click(
      screen.getByRole("radio", { name: firstQuestion.choices[0].text }),
    );
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    const impact = await screen.findByRole("region", { name: "What changed?" });
    const table = within(impact).getByRole("table");
    expect(within(impact).getByText(fixture.assessment.feedback)).toBeTruthy();
    expect(within(impact).getByText(fixture.decision.reason)).toBeTruthy();
    expect(within(impact).getByText("Worked example")).toBeTruthy();
    expect(within(impact).getByText(fixture.next_question.prompt)).toBeTruthy();
    expect(
      within(table).getByRole("row", { name: "Estimate 50.0% 33.3%" }),
    ).toBeTruthy();
    expect(
      within(table).getByRole("row", {
        name: "90% uncertainty range 5.0% – 95.0% 2.5% – 77.6%",
      }),
    ).toBeTruthy();
    expect(
      within(table).getByRole("row", {
        name: "Interval width 90.0 pp 75.1 pp",
      }),
    ).toBeTruthy();
    expect(
      within(table).getByRole("row", { name: "Observations 0 1" }),
    ).toBeTruthy();
    expect(within(impact).getByText(/New observation recorded/)).toBeTruthy();
    expect(
      within(impact).getByText(/comparable unaided questions/),
    ).toBeTruthy();
    expect(
      within(screen.getByRole("tabpanel", { name: "Study desk" })).getByText(
        "Deterministic teaching",
      ),
    ).toBeTruthy();
    expect(document.activeElement).toBe(
      screen.getByRole("heading", { name: "Here’s the useful distinction." }),
    );
    const values = table.textContent;
    await user.click(screen.getByRole("switch", { name: /Keep it concise/ }));
    expect(table.textContent).toBe(values);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    await user.click(
      screen.getByRole("button", { name: "Try the next question" }),
    );
    await user.click(
      screen.getByRole("radio", { name: "Admissible, but not consistent." }),
    );
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    const finalImpact = await screen.findByRole("region", {
      name: "What changed?",
    });
    expect(
      within(finalImpact).getByRole("row", { name: "Estimate 33.3% 50.0%" }),
    ).toBeTruthy();
    expect(
      within(finalImpact).getByRole("row", {
        name: "Interval width 75.1 pp 72.9 pp",
      }),
    ).toBeTruthy();
    expect(
      within(finalImpact).getByRole("row", { name: "Observations 1 2" }),
    ).toBeTruthy();
    expect(within(finalImpact).getByText("Session complete")).toBeTruthy();
    expect(within(finalImpact).queryByText("Next strategy")).toBeNull();
    expect(
      within(finalImpact).getByText(/No next question was returned/),
    ).toBeTruthy();
  });

  it("reports unchanged evidence without guessing a cause, and labels returned fallback teaching", async () => {
    fetchMock.mockResolvedValueOnce(
      respond({
        ...fixture,
        concepts: initial.concepts,
        assessment: {
          outcome: "unclear",
          misconception_id: null,
          feedback: "Try another example.",
        },
        tutor: {
          text: "This text mentions Bedrock but is still a marked fallback.",
          fallback: true,
        },
      }),
    );
    const user = await start();
    await user.click(screen.getByRole("radio", { name: "I'm not sure yet." }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    const impact = await screen.findByRole("region", { name: "What changed?" });
    expect(
      within(impact).getByRole("row", { name: "Observations 0 0" }),
    ).toBeTruthy();
    expect(
      within(impact).getByRole("row", {
        name: "Interval width 90.0 pp 90.0 pp",
      }),
    ).toBeTruthy();
    expect(
      within(impact).getByText(
        "No new observation recorded. The understanding estimate is unchanged.",
      ),
    ).toBeTruthy();
    expect(
      within(impact).getByText(/No evidence yet for this concept/),
    ).toBeTruthy();
    expect(
      within(screen.getByRole("tabpanel", { name: "Study desk" })).getByText(
        "Marked fallback teaching",
      ),
    ).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Read explanation" }));
    const conversation = screen.getByRole("region", {
      name: "Study conversation",
    });
    expect(
      within(conversation).getByText("Marked fallback teaching"),
    ).toBeTruthy();
    expect(
      within(conversation).queryByText("Deterministic teaching"),
    ).toBeNull();
    expect(within(conversation).queryByText(/live.*generated/i)).toBeNull();
    expect(within(conversation).queryByText(/reviewed fallback/i)).toBeNull();
  });

  it("exposes current concept uncertainty and only the responses from this session", async () => {
    fetchMock.mockResolvedValueOnce(respond(fixture));
    const user = await start();
    await user.click(screen.getByRole("tab", { name: "Concept map" }));
    const empty = screen.getByRole("region", {
      name: "Selected concept evidence",
    });
    expect(
      within(empty).getByText(/No evidence yet; this is a starting estimate/),
    ).toBeTruthy();
    expect(
      within(empty).getByText("No responses for this concept in this session."),
    ).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Study desk" }));
    await user.click(
      screen.getByRole("radio", { name: firstQuestion.choices[0].text }),
    );
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    await screen.findByRole("region", { name: "What changed?" });
    await user.click(screen.getByRole("tab", { name: "Concept map" }));
    const selected = screen.getByRole("region", {
      name: "Selected concept evidence",
    });
    expect(within(selected).getByText("33.3%")).toBeTruthy();
    expect(within(selected).getByText("2.5% – 77.6%")).toBeTruthy();
    expect(within(selected).getByText("75.1 percentage points")).toBeTruthy();
    const history = screen.getByRole("region", {
      name: "Answers for this concept",
    });
    expect(within(history).getByText(fixture.assessment.feedback)).toBeTruthy();
    await user.click(
      within(screen.getByRole("tabpanel", { name: "Concept map" })).getByRole(
        "button",
        { name: /BFS/ },
      ),
    );
    expect(
      screen.queryByRole("region", { name: "Answers for this concept" }),
    ).toBeNull();
    expect(
      screen.getByText("No responses for this concept in this session."),
    ).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("uses the current existing token on creation and reset without changing request payloads", async () => {
    const setToken = (token?: string) =>
      window.sessionStorage.setItem(
        "minds-machines-auth",
        JSON.stringify({
          email: "test@example.com",
          signedInAt: "2026-09-16T00:00:00Z",
          idToken: token,
        }),
      );
    setToken("synthetic-initial-token");
    fetchMock
      .mockResolvedValueOnce(respond(fixture))
      .mockResolvedValueOnce(respond(initial))
      .mockResolvedValueOnce(respond(initial));
    const user = await start();
    expect(fetchMock.mock.calls[0][1].headers).toEqual({
      "Content-Type": "application/json",
      Authorization: "Bearer synthetic-initial-token",
    });
    expect(fetchMock.mock.calls[0][1].body).toBe("{}");
    await user.click(
      screen.getByRole("radio", { name: firstQuestion.choices[0].text }),
    );
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    await screen.findByRole("region", { name: "What changed?" });
    // Current backend /turns does not consume Authorization; do not claim it is authenticated.
    expect(fetchMock.mock.calls[1][1].headers).toEqual({
      "Content-Type": "application/json",
    });
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({
      session_id: initial.session_id,
      question_id: firstQuestion.question_id,
      answer: "a",
      presentation_preferences: {
        plain_language: false,
        step_by_step: false,
        concise: false,
      },
    });
    setToken("synthetic-current-token");
    await user.click(
      screen.getByRole("button", { name: "New session / reset" }),
    );
    await screen.findByRole("radio", { name: firstQuestion.choices[0].text });
    expect(fetchMock.mock.calls[2][1].headers.Authorization).toBe(
      "Bearer synthetic-current-token",
    );
    expect(fetchMock.mock.calls[2][1].body).toBe("{}");
    setToken();
    await user.click(
      screen.getByRole("button", { name: "New session / reset" }),
    );
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    expect(fetchMock.mock.calls[3][1].headers).toEqual({
      "Content-Type": "application/json",
    });
    expect(fetchMock.mock.calls[3][1].body).toBe("{}");
  });
});
