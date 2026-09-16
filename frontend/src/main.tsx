import { createRoot } from 'react-dom/client';
import { useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import type {
  ConceptEstimate, LearnerPresentationPreferences, PublicQuestion, SessionResponse,
  TurnRequest, TurnResponse,
} from '../../contracts/api';
import './style.css';

const conceptNames: Record<string, string> = {
  bfs: 'Breadth-first search', ucs: 'Uniform-cost search', astar: 'A* search',
  admissibility: 'Admissibility', consistency: 'Consistency',
  admissibility_vs_consistency: 'Admissibility vs consistency',
};
const defaults: LearnerPresentationPreferences = { plain_language: false, step_by_step: false, concise: false };
const preferenceLabels: [keyof LearnerPresentationPreferences, string][] = [
  ['plain_language', 'Plain language / explain jargon'],
  ['step_by_step', 'Step-by-step'], ['concise', 'Concise'],
];
const stageNames: Record<string, string> = {
  assess: 'FakeAssessor', update: 'FakeLearner', select: 'FakePolicy', teach: 'FakeTutor',
};
const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

async function post<T>(path: string, body: object): Promise<T> {
  const response = await fetch(`/api/v1/${path}`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(typeof payload?.detail === 'string' ? payload.detail : 'Unable to continue. Please start a new session.');
  }
  return response.json();
}

function App() {
  const [sessionId, setSessionId] = useState('');
  const [question, setQuestion] = useState<PublicQuestion | null>(null);
  const [concepts, setConcepts] = useState<ConceptEstimate[]>([]);
  const [turn, setTurn] = useState<TurnResponse | null>(null);
  const [answer, setAnswer] = useState('');
  const [preferences, setPreferences] = useState(defaults);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [answered, setAnswered] = useState(0);
  const resultHeading = useRef<HTMLHeadingElement>(null);

  async function newSession() {
    setBusy(true); setError('');
    try {
      const result = await post<SessionResponse>('sessions', {});
      setSessionId(result.session_id); setQuestion(result.question); setConcepts(result.concepts);
      setTurn(null); setAnswer(''); setAnswered(0);
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }
  useEffect(() => { void newSession(); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question || !answer || busy) return;
    setBusy(true); setError('');
    const request: TurnRequest = {
      session_id: sessionId, question_id: question.question_id, answer,
      presentation_preferences: preferences,
    };
    try {
      const result = await post<TurnResponse>('turns', request);
      setTurn(result); setConcepts(result.concepts); setQuestion(result.next_question);
      setAnswer(''); setAnswered(value => value + 1);
      requestAnimationFrame(() => resultHeading.current?.focus());
    } catch (err) { setError((err as Error).message); }
    finally { setBusy(false); }
  }

  return <>
    <a className="skip-link" href="#question">Skip to question</a>
    <header className="topbar">
      <a className="brand" href="/" aria-label="Minds and Machines home"><span className="brand-mark" aria-hidden="true">m.</span> Minds & Machines</a>
      <span className="mode"><span aria-hidden="true" /> Deterministic demo · no live AI</span>
    </header>
    <main>
      <div className="intro">
        <div><p className="eyebrow">THE LEARNING LAB / INTRO TO AI</p><h1>Make the distinction.<br /><span>Build understanding.</span></h1>
          <p className="intro-copy">A small learning loop that makes every next step visible.</p></div>
        <button className="reset" onClick={() => void newSession()} disabled={busy}>↻ New session / reset</button>
      </div>
      <div className="workspace">
        <div className="lesson-column">
          <section className="card question-card" id="question" aria-labelledby="question-title" aria-busy={busy}>
            <div className="card-top"><span className="eyebrow">SEARCH / INFORMED SEARCH</span><span className="count">{question ? `${answered + 1} / 2` : '2 / 2'}</span></div>
            <h2 id="question-title">{question ? 'Admissibility vs consistency' : sessionId ? 'A small step, made visible.' : 'Starting your session…'}</h2>
            {question ? <form onSubmit={submit}>
              <fieldset disabled={busy}><legend className="prompt">{question.prompt}</legend>
                <div className="choices">{question.choices.map((choice, index) => <label className={`choice ${answer === choice.id ? 'selected' : ''}`} key={choice.id}>
                  <input type="radio" name="answer" value={choice.id} checked={answer === choice.id} onChange={() => setAnswer(choice.id)} />
                  <span className="choice-letter" aria-hidden="true">{String.fromCharCode(65 + index)}</span><span>{choice.text}</span>
                </label>)}</div>
              </fieldset>
              <div className="question-footer"><span>Take your time. Uncertainty is welcome.</span><button className="primary" disabled={!answer || busy}>{busy ? 'Working…' : 'Check answer →'}</button></div>
            </form> : sessionId ? <p className="completion">You’ve completed this two-question loop. Your estimates are still experimental. Reset to replay the same evidence with a different explanation style.</p> : null}
            {error && <p className="error" role="alert">{error}</p>}
          </section>

          {turn ? <section className="card response-card" aria-labelledby="result-title">
            <div className="card-top"><p className={`result-tag ${turn.assessment.outcome}`}>{turn.assessment.outcome === 'correct' ? '✓ Correct' : turn.assessment.outcome === 'incorrect' ? '↗ Incorrect · a useful misconception' : '○ Not sure yet'}</p><span className="eyebrow">ANSWER {answered}</span></div>
            <h2 id="result-title" tabIndex={-1} ref={resultHeading}>Your answer, understood.</h2>
            <p>{turn.assessment.feedback}</p>
            {turn.assessment.misconception_id && <p className="diagnosis"><strong>Diagnosis</strong> · Treating “admissible” as a guarantee of “consistent”.</p>}
            <div className="decision"><span className="eyebrow">WHY THIS NEXT?</span><h3>{turn.decision ? ({worked_example: 'Worked example', diagnostic_probe: 'Diagnostic probe', socratic_hint: 'Socratic hint'}[turn.decision.kind]) : 'Demo complete'}</h3>
              <p>{turn.decision?.reason ?? 'Both questions have been presented. Start a new session to replay the fixed baseline.'}</p>
            </div>
            <div className="tutor"><div className="tutor-label"><span className="tutor-mark" aria-hidden="true">m.</span><h3>Tutor response</h3>{turn.tutor.fallback && <span className="fallback">Canned fallback</span>}</div>
              <p className="tutor-text">{turn.tutor.text}</p>
            </div>
            <div className="trace"><span className="eyebrow">THE PATH THIS ANSWER TOOK</span><ol>{turn.trace.map((stage, index) => <li key={stage}><span>{index + 1}</span>{stageNames[stage] ?? stage}</li>)}</ol></div>
          </section> : <section className="card awaiting"><span className="small-star" aria-hidden="true">✳</span><div><h2>Teaching that follows the evidence.</h2><p>Submit an answer to see a diagnosis, a targeted estimate change, and a reason for the next activity.</p></div></section>}
        </div>
        <aside>
          <section className="card knowledge" aria-labelledby="knowledge-title">
            <p className="eyebrow">YOUR CONCEPT MAP</p><h2 id="knowledge-title">What we know so far</h2>
            <p className="muted">Mastery estimates for six concepts. Each answer supplies evidence for just one.</p>
            <div className="concept-list">{concepts.map(concept => <div className={`concept ${concept.concept_id === 'admissibility_vs_consistency' ? 'target' : ''}`} key={concept.concept_id}>
              <div className="concept-name"><span>{conceptNames[concept.concept_id]}</span><strong>{pct(concept.mean)}</strong></div>
              <div className="estimate-bar" aria-hidden="true"><span className="interval-bar" style={{ left: pct(concept.interval90.lower), width: pct(concept.interval90.upper - concept.interval90.lower) }} /><span className="mean-tick" style={{ left: pct(concept.mean) }} /></div>
              <div className="estimate-detail"><span>90% interval {pct(concept.interval90.lower)}–{pct(concept.interval90.upper)}</span><span>{concept.evidence_count} evidence</span></div>
            </div>)}</div>
            <p className="model-note"><strong>Experimental, not a grade.</strong> Predicted success on similar unaided questions. All values here are canned demo fixtures; no learning model is running.</p>
          </section>
          <section className="card preferences" aria-labelledby="preferences-title">
            <p className="eyebrow">MAKE IT YOURS</p><h2 id="preferences-title">How you like to learn</h2>
            <p className="muted">Change the explanation, not your knowledge estimate.</p>
            <fieldset disabled={busy}><legend className="sr-only">Learner presentation preferences</legend>
              {preferenceLabels.map(([key, label]) => <label className="preference" key={key}><input type="checkbox" checked={preferences[key]} onChange={event => setPreferences({ ...preferences, [key]: event.target.checked })} /><span>{label}</span></label>)}
            </fieldset>
            <p className="preference-note">Applies to the next tutor response. Your choices stay selected when you reset.</p>
          </section>
        </aside>
      </div>
      <footer><span>MINDS & MACHINES</span><span>G1 baseline · two questions · four replaceable fakes</span></footer>
    </main>
  </>;
}

createRoot(document.getElementById('root')!).render(<App />);
