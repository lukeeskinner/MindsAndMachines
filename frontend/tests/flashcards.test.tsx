// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { App } from "../src/App";
import { Flashcards } from "../src/components/study/Flashcards";
import type { Flashcard } from "../../contracts/api";

const cards: Flashcard[] = [
  { card_id: "a", concept_id: "bfs", front: "Recall breadth-first search", back: "Explore by depth.", source: "Search notes" },
  { card_id: "b", concept_id: "ucs", front: "Recall uniform-cost search", back: "Explore by accumulated cost.", source: "Search notes" },
];
const names = { bfs: "BFS", ucs: "UCS" };
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("browses both directions without rating skipped cards or leaving answers revealed", async () => {
  const user = userEvent.setup();
  render(<Flashcards cards={cards} names={names} />);
  expect((screen.getByRole("button", { name: "Previous card" }) as HTMLButtonElement).disabled).toBe(true);
  await user.click(screen.getByRole("button", { name: "Show answer" }));
  await user.click(screen.getByRole("button", { name: "Next card" }));
  expect(screen.getByRole("heading", { name: cards[1].front })).toBeTruthy();
  expect(screen.queryByRole("region", { name: "Card answer" })).toBeNull();
  expect((screen.getByRole("button", { name: "Next card" }) as HTMLButtonElement).disabled).toBe(true);
  expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("0");
  await user.click(screen.getByRole("button", { name: "Previous card" }));
  expect(screen.getByRole("heading", { name: cards[0].front })).toBeTruthy();
  expect(screen.queryByRole("region", { name: "Card answer" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "Next card" }));
  await user.click(screen.getByRole("button", { name: "Show answer" }));
  await user.click(screen.getByRole("button", { name: "Got it" }));
  expect(screen.getByRole("heading", { name: cards[0].front })).toBeTruthy();
  expect(screen.queryByText("DECK COMPLETE")).toBeNull();
  expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("1");
});

it("reveals cards before self-rating and repeats only the requested cards", async () => {
  const user = userEvent.setup();
  render(<Flashcards cards={cards} names={names} />);
  expect(screen.queryByText(cards[0].back)).toBeNull();
  expect(screen.queryByRole("button", { name: "Got it" })).toBeNull();
  await user.click(screen.getByRole("button", { name: "Show answer" }));
  expect(within(screen.getByRole("region", { name: "Card answer" })).getByText(cards[0].back)).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Review again", exact: true }));
  expect(screen.getByRole("heading", { name: cards[1].front })).toBeTruthy();
  expect(screen.queryByText(cards[1].back)).toBeNull();
  await user.click(screen.getByRole("button", { name: "Show answer" }));
  await user.click(screen.getByRole("button", { name: "Got it" }));
  expect(screen.getByText('You marked 1 of 2 cards “Got it”.')).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Review 1 card again" }));
  expect(screen.getByRole("heading", { name: cards[0].front })).toBeTruthy();
  expect(screen.getByRole("progressbar").getAttribute("aria-valuemax")).toBe("1");
  await user.selectOptions(screen.getByRole("combobox", { name: "Topic" }), "ucs");
  expect(screen.getByRole("heading", { name: cards[1].front })).toBeTruthy();
});

it("preserves the quiz answer and flashcard position across modes and navigation without submitting evidence", async () => {
  const user = userEvent.setup();
  const session = { session_id: "study-test", course_id: null, question_count: 8, flashcards: cards,
    question: { question_id: "q1", concept_id: "bfs", prompt: "Choose a search strategy", choices: [{ id: "a", text: "Breadth first" }] },
    concepts: [{ concept_id: "bfs", mean: .5, interval90: { lower: .05, upper: .95 }, evidence_count: 0 }] };
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => session })
    .mockResolvedValue({ ok: true, json: async () => ({ ...session, session_id: "reset-session" }) });
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  await user.click(await screen.findByRole("radio", { name: "Breadth first" }));
  expect(screen.getByText("Question 1 of 8")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Flashcards", exact: true }));
  await user.click(screen.getByRole("button", { name: "Show answer" }));
  await user.click(screen.getByRole("button", { name: "Got it" }));
  await user.click(screen.getByRole("tab", { name: "Home", exact: true }));
  await user.click(screen.getByRole("tab", { name: "Study desk", exact: true }));
  expect(screen.getByRole("heading", { name: cards[1].front })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Practice quiz" }));
  expect((screen.getByRole("radio", { name: "Breadth first" }) as HTMLInputElement).checked).toBe(true);
  expect(fetch).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole("button", { name: "New practice session" }));
  await user.click(await screen.findByRole("button", { name: "Flashcards", exact: true }));
  expect(screen.getByRole("heading", { name: cards[0].front })).toBeTruthy();
  expect(fetch).toHaveBeenCalledTimes(2);
});
