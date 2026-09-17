// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Flashcards } from "../src/components/study/Flashcards";
import { App } from "../src/App";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("preserves review position, reveal and ratings when a turn returns an unchanged deck", async () => {
  const user = userEvent.setup();
  const cards = [
    { card_id: "one", concept_id: "x", front: "First idea", back: "First explanation", source: "Notes" },
    { card_id: "two", concept_id: "y", front: "Second idea", back: "Second explanation", source: "Notes" },
  ];
  const { rerender } = render(<Flashcards cards={cards} names={{}} />);
  await user.click(screen.getByRole("button", { name: "Show answer" }));
  await user.click(screen.getByRole("button", { name: "Got it" }));
  await user.click(screen.getByRole("button", { name: "Show answer" }));
  // An unsure/no-focus response contains fresh JSON objects but unchanged cards.
  rerender(<Flashcards cards={cards.map(card => ({ ...card }))} names={{}} />);
  expect(screen.getByRole("heading", { name: "Second idea" })).toBeTruthy();
  expect(screen.getByRole("region", { name: "Card answer" }).textContent).toContain("Second explanation");
  expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("1");
});

it("accepts server priority changes, preserves self-ratings, and hides revealed answers", async () => {
  const user = userEvent.setup();
  const cards = [
    { card_id: "one", concept_id: "x", front: "First idea", back: "First explanation", source: "Notes" },
    { card_id: "two", concept_id: "y", front: "Weak idea", back: "Second explanation", source: "Notes" },
  ];
  const { rerender } = render(<Flashcards cards={cards} names={{}} />);
  await user.click(screen.getByRole("button", { name: "Show answer" }));
  await user.click(screen.getByRole("button", { name: "Got it" }));
  await user.click(screen.getByRole("button", { name: "Show answer" }));
  rerender(<Flashcards cards={[cards[1], cards[0]]} names={{}} />);
  expect(screen.getByRole("heading", { name: "Weak idea" })).toBeTruthy();
  expect(screen.queryByRole("region", { name: "Card answer" })).toBeNull();
  expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("1");
  await user.selectOptions(screen.getByRole("combobox"), "x");
  rerender(<Flashcards cards={[cards[1], cards[0]]} names={{}} />);
  expect(screen.getByRole("heading", { name: "First idea" })).toBeTruthy();
});

it("shows turn-ranked review cards in the existing workspace without submitting card evidence", async () => {
  const user = userEvent.setup();
  const cards = [
    { card_id: "one", concept_id: "bfs", front: "First topic", back: "First notes", source: "Notes" },
    { card_id: "two", concept_id: "ucs", front: "Review the weak topic", back: "Review notes", source: "Notes" },
  ];
  const question = { question_id: "q1", concept_id: "ucs", prompt: "Choose an approach",
    choices: [{ id: "a", text: "First approach" }] };
  const concepts = ["bfs", "ucs"].map(concept_id => ({ concept_id, mean: .5,
    interval90: { lower: .05, upper: .95 }, evidence_count: 0 }));
  const session = { session_id: "adaptive", course_id: null, question_count: 2, question, concepts, flashcards: cards };
  const response = { session_id: "adaptive", assessment: { outcome: "incorrect", misconception_id: null, feedback: "Review the topic." },
    concepts: concepts.map(c => c.concept_id === "ucs" ? { ...c, mean: 1 / 3, evidence_count: 1 } : c),
    decision: null, tutor: { text: "Review the conditions.", fallback: false, teaching_source: "authored" },
    next_question: { ...question, question_id: "q2" }, mode: "dummy", provider: "fake",
    trace: ["assess", "update", "select", "teach"], flashcards: [cards[1], cards[0]] };
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => session })
    .mockResolvedValueOnce({ ok: true, json: async () => response });
  vi.stubGlobal("fetch", fetch);
  render(<App />);
  await user.click(await screen.findByRole("radio", { name: "First approach" }));
  await user.click(screen.getByRole("button", { name: "Check answer" }));
  await user.click(await screen.findByRole("button", { name: "Flashcards", exact: true }));
  expect(screen.getByRole("heading", { name: "Review the weak topic" })).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "Show answer" }));
  await user.click(screen.getByRole("button", { name: "Got it" }));
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("rotates within a weak concept when updated priority would repeat the current card", async () => {
 const cards = [1,2,3].map(i=>({card_id:String(i),concept_id:"weak",front:`Idea ${i}`,back:`Detail ${i}`,source:"Notes"}));
 const {rerender}=render(<Flashcards cards={cards} names={{weak:"Weak concept"}}/>);
 expect(screen.getByRole("heading",{name:"Idea 1"})).toBeTruthy();
 rerender(<Flashcards cards={[cards[0],cards[2],cards[1]]} names={{weak:"Weak concept"}}/>);
 expect(screen.getByRole("heading",{name:"Idea 3"})).toBeTruthy();
});
