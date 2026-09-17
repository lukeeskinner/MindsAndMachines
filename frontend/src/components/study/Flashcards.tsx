import { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Check, Layers3, RotateCcw } from "lucide-react";
import type { Flashcard } from "../../../../contracts/api";
import { Button, Scene } from "../ui/primitives";
import "./flashcards.css";

export function Flashcards({ cards, names }: { cards: Flashcard[]; names: Record<string, string> }) {
  const [filter, setFilter] = useState("");
  const [deck, setDeck] = useState(cards);
  const [index, setIndex] = useState(0);
  const [revealed, setRevealed] = useState(false);
  const [ratings, setRatings] = useState<Record<string, "again" | "got">>({});
  const again = deck.filter(card => ratings[card.card_id] === "again");
  const reviewed = deck.filter(card => ratings[card.card_id]).length;
  const heading = useRef<HTMLHeadingElement>(null);
  const previousCards = useRef(cards);
  const card = deck[index];
  const ids = [...new Set(cards.map(c => c.concept_id))];
  useEffect(() => {
    const unchanged = previousCards.current.length === cards.length &&
      previousCards.current.every((card, index) =>
        (["card_id", "concept_id", "front", "back", "source"] as const)
          .every(field => card[field] === cards[index][field]));
    previousCards.current = cards;
    if (unchanged) return;
    // Refresh only when card content/order changes. An unchanged deck from a
    // quiz turn preserves browsing, reveal, self-ratings and review-again passes.
    const next = cards.filter(c => !filter || c.concept_id === filter);
    if (next[0]?.card_id === card?.card_id) {
      const alternative = next.findIndex(c => c.concept_id === card.concept_id && c.card_id !== card.card_id);
      if (alternative > 0) [next[0], next[alternative]] = [next[alternative], next[0]];
    }
    setDeck(next);
    setIndex(0); setRevealed(false);
  }, [cards]);
  useEffect(() => { if (index > 0) heading.current?.focus({ preventScroll: true }); }, [index]);

  function start(next: Flashcard[]) {
    setDeck(next); setIndex(0); setRevealed(false); setRatings({});
  }
  function browse(next: number) {
    if (next < 0 || next >= deck.length) return;
    setRevealed(false); setIndex(next);
  }
  function rate(repeat: boolean) {
    if (!card || !revealed) return;
    const nextRatings = { ...ratings, [card.card_id]: repeat ? "again" as const : "got" as const };
    setRatings(nextRatings);
    // Browsing does not count as review. Visit any skipped cards before finishing.
    const remaining = [...deck.slice(index + 1), ...deck.slice(0, index)]
      .find(item => !nextRatings[item.card_id]);
    setRevealed(false);
    setIndex(remaining ? deck.indexOf(remaining) : deck.length);
  }
  if (!cards.length) return <section className="study-surface empty-state">
    <Layers3 size={28} /><h2>Flashcards are not available for this session.</h2>
    <p>Start a new session to load the course’s study deck.</p>
  </section>;

  return <section className="flashcards" aria-label="Flashcard study">
    <div className="flashcard-toolbar">
      <label>Topic<select value={filter} onChange={event => {
        const value = event.target.value; setFilter(value);
        start(cards.filter(c => !value || c.concept_id === value));
      }}><option value="">All topics</option>{ids.map(id => <option key={id} value={id}>{names[id] ?? id}</option>)}</select></label>
      <div className="flashcard-navigation" role="group" aria-label="Browse flashcards">
        <Button variant="ghost" aria-label="Previous card" title="Previous card"
          disabled={index === 0} onClick={() => browse(index - 1)}><ArrowLeft size={18} /></Button>
        <span>{deck.length} {deck.length === 1 ? "card" : "cards"}</span>
        <Button variant="ghost" aria-label="Next card" title="Next card"
          disabled={index >= deck.length - 1} onClick={() => browse(index + 1)}><ArrowRight size={18} /></Button>
      </div>
    </div>
    <div className="flashcard-progress" role="progressbar" aria-label="Cards reviewed"
      aria-valuemin={0} aria-valuemax={deck.length} aria-valuenow={reviewed}>
      <span style={{ width: `${reviewed / deck.length * 100}%` }} />
    </div>
    {card ? <Scene key={card.card_id}>
      <article className="flashcard-surface">
        <div className="surface-meta"><span><Layers3 size={16} /> {names[card.concept_id] ?? card.concept_id}</span><span>{index + 1} / {deck.length}</span></div>
        <p className="eyebrow">{revealed ? "CONNECT THE IDEA" : "TRY TO RECALL"}</p>
        <h2 ref={heading} tabIndex={-1}>{card.front}</h2>
        {revealed ? <div className="flashcard-answer" role="region" aria-label="Card answer" aria-live="polite">
          <p>{card.back}</p><small>{card.source}</small>
        </div> : <p className="flashcard-prompt">Think it through, then turn the card.</p>}
        <div className="flashcard-actions">
          {revealed ? <><Button variant="secondary" onClick={() => rate(true)}><RotateCcw size={16} />Review again</Button>
            <Button onClick={() => rate(false)}>Got it<Check size={16} /></Button></>
            : <Button onClick={() => setRevealed(true)}>Show answer<ArrowRight size={16} /></Button>}
        </div>
      </article>
    </Scene> : <section className="flashcard-surface flashcard-complete" aria-live="polite">
      <Check size={30} /><p className="eyebrow">DECK COMPLETE</p>
      <h2 ref={heading} tabIndex={-1}>A few ideas, a little clearer.</h2>
      <p>You marked {deck.length - again.length} of {deck.length} cards “Got it”.</p>
      <div className="flashcard-actions">
        {!!again.length && <Button onClick={() => start(again)}>Review {again.length} {again.length === 1 ? "card" : "cards"} again<ArrowRight size={16} /></Button>}
        <Button variant="secondary" onClick={() => start(cards.filter(c => !filter || c.concept_id === filter))}><RotateCcw size={16} />Restart deck</Button>
      </div>
    </section>}
    <p className="flashcard-note">Self-review for this session. Your quiz estimates change only when you answer practice questions.</p>
  </section>;
}
