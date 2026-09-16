import { useEffect, useRef, useState, type FormEvent } from "react";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCheck,
  ChevronRight,
  CircleHelp,
  GitBranch,
  History,
  Info,
  Layers3,
  LoaderCircle,
  MessageSquare,
  Network,
  RotateCcw,
  Terminal,
  Waypoints,
} from "lucide-react";
import type {
  ConceptEstimate,
  LearnerPresentationPreferences,
  PublicQuestion,
  SessionResponse,
  TurnRequest,
  TurnResponse,
} from "../../contracts/api";
import {
  Button,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Disclosure,
  Scene,
} from "./components/ui/primitives";
import { motion, MotionConfig, useReducedMotion } from "motion/react";
import { post } from "./lib/api";
import { getIdToken } from "./auth/cognito";
import { StudyChatbot } from "./components/study/StudyChatbot";
import { EvidenceComparison } from "./components/study/EvidenceComparison";
import { TeachingPreferences } from "./components/study/TeachingPreferences";
import {
  conceptNames as names,
  type StudyEntry,
} from "./components/study/model";

const shortNames: Record<string, string> = {
  bfs: "BFS",
  ucs: "UCS",
  astar: "A*",
  admissibility: "Admissibility",
  consistency: "Consistency",
  admissibility_vs_consistency: "The connection",
};
const stages: Record<string, [string, string]> = {
  assess: ["Assessment", "FakeAssessor"],
  update: ["Concept estimate", "BayesianLearner"],
  select: ["Next activity", "AdaptivePolicy"],
  teach: ["Teaching response", "FakeTutor"],
};
const activityNames = {
  worked_example: "Worked example",
  diagnostic_probe: "Diagnostic probe",
  socratic_hint: "Socratic hint",
};
const focusConcept = "admissibility_vs_consistency";
const groups = [
  { name: "Search strategies", ids: ["bfs", "ucs", "astar"] },
  {
    name: "Heuristic properties",
    ids: ["admissibility", "consistency", focusConcept],
  },
];
const defaults: LearnerPresentationPreferences = {
  plain_language: false,
  step_by_step: false,
  concise: false,
};
const pct = (value: number) => `${(value * 100).toFixed(1)}%`;

function Estimate({ concept }: { concept: ConceptEstimate }) {
  const reduced = useReducedMotion();
  return (
    <div className="estimate">
      <div className="estimate-track" aria-hidden="true">
        <motion.span
          className="estimate-range"
          initial={false}
          transition={{ duration: reduced ? 0 : 0.35 }}
          animate={{
            left: pct(concept.interval90.lower),
            width: pct(concept.interval90.upper - concept.interval90.lower),
          }}
        />
        <motion.span
          className="estimate-point"
          initial={false}
          animate={{ left: pct(concept.mean) }}
          transition={{ duration: reduced ? 0 : 0.35 }}
        />
      </div>
      <div className="estimate-labels">
        <span>90% interval</span>
        <span>
          {pct(concept.interval90.lower)}–{pct(concept.interval90.upper)}
        </span>
      </div>
    </div>
  );
}
function Outcome({ result }: { result: TurnResponse }) {
  return (
    <span className={`outcome outcome-${result.assessment.outcome}`}>
      {result.assessment.outcome === "correct" ? (
        <CheckCheck size={16} />
      ) : (
        <CircleHelp size={16} />
      )}
      {result.assessment.outcome === "correct"
        ? "Correct"
        : result.assessment.outcome === "incorrect"
          ? "Not quite — let’s unpack it"
          : "Not sure yet"}
    </span>
  );
}
function Trace({ result }: { result: TurnResponse }) {
  return (
    <Disclosure title="Behind this response">
      <p className="subtle">
        Deterministic mode · {result.provider} provider. Bayesian estimates and
        adaptive selection; assessment and teaching remain fake. No live AI agents.
      </p>
      <ol className="trace-list">
        {result.trace.map((stage, index) => (
          <li key={`${stage}-${index}`}>
            <Check size={14} aria-hidden="true" />
            <span>
              {stages[stage]?.[0] ?? stage}
              <small>{stages[stage]?.[1] ?? stage}</small>
            </span>
          </li>
        ))}
      </ol>
    </Disclosure>
  );
}

export function App({ onEditSetup }: { onEditSetup?: () => void } = {}) {
  const [sessionId, setSessionId] = useState("");
  const [question, setQuestion] = useState<PublicQuestion | null>(null);
  const [concepts, setConcepts] = useState<ConceptEstimate[]>([]);
  const [entries, setEntries] = useState<StudyEntry[]>([]);
  const [answer, setAnswer] = useState("");
  const [preferences, setPreferences] = useState(defaults);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [view, setView] = useState("study");
  const [orientation, setOrientation] = useState<"vertical" | "horizontal">(
    "vertical",
  );
  const [reviewing, setReviewing] = useState(false);
  const [selectedConcept, setSelectedConcept] = useState(focusConcept);
  const requestInFlight = useRef(false);
  const focusHeading = useRef<HTMLHeadingElement>(null);
  const latest = entries.at(-1);
  const selected = concepts.find(
    (concept) => concept.concept_id === selectedConcept,
  );
  const complete = !!sessionId && !question;
  const review = reviewing ? latest : undefined;

  async function newSession() {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const token = getIdToken();
      const result = await post<SessionResponse>("sessions", {}, token ? `Bearer ${token}` : undefined);
      setSessionId(result.session_id);
      setQuestion(result.question);
      setConcepts(result.concepts);
      setEntries([]);
      setAnswer("");
      setReviewing(false);
      setView("study");
      setSelectedConcept(focusConcept);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to start your session.",
      );
    } finally {
      requestInFlight.current = false;
      setBusy(false);
    }
  }
  useEffect(() => {
    void newSession();
  }, []);
  useEffect(() => {
    if (!window.matchMedia) return;
    const media = window.matchMedia("(max-width: 560px)");
    const update = () =>
      setOrientation(media.matches ? "horizontal" : "vertical");
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    if (view === "study" && entries.length)
      focusHeading.current?.focus({ preventScroll: true });
  }, [reviewing, entries.length, view]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!question || !answer || requestInFlight.current || error) return;
    requestInFlight.current = true;
    setBusy(true);
    setError("");
    const request: TurnRequest = {
      session_id: sessionId,
      question_id: question.question_id,
      answer,
      presentation_preferences: preferences,
    };
    try {
      const result = await post<TurnResponse>("turns", request);
      setEntries((previous) => [
        ...previous,
        { question, answer, result, before: concepts },
      ]);
      setConcepts(result.concepts);
      setQuestion(result.next_question);
      setAnswer("");
      setReviewing(true);
      setSelectedConcept(question.concept_id);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to check your answer.",
      );
    } finally {
      requestInFlight.current = false;
      setBusy(false);
    }
  }

  function openChatbot() {
    setView("chatbot");
    requestAnimationFrame(() =>
      document.getElementById("chatbot-title")?.focus(),
    );
  }

  return (
    <MotionConfig reducedMotion="user">
      <Tabs
        value={view}
        onValueChange={setView}
        className="app-shell workspace-with-chat"
        orientation={orientation}
      >
        <a className="skip-link" href="#workspace">
          Skip to workspace
        </a>
        <aside className="navigation">
          <a
            className="brand"
            href={onEditSetup ? "#/setup" : "/"}
            aria-label="Minds and Machines home"
          >
            <span className="brand-mark">
              <Waypoints size={24} strokeWidth={1.8} />
            </span>
            <span>
              minds<span className="brand-amp"> & </span>
              <br />
              machines<span className="brand-dot">.</span>
            </span>
          </a>
          <div className="course-label">YOUR WORKSPACE</div>
          <div className="course">
            <span className="course-icon">
              <BookOpen size={18} />
            </span>
            <span>
              Introduction to AI<small>Search & heuristics</small>
            </span>
          </div>
          <TabsList className="navigation-list" aria-label="Learning workspace">
            <TabsTrigger
              value="study"
              className="nav-item"
              aria-label="Study desk"
            >
              <BookOpen size={19} />
              Study desk
              <span className="nav-active-dot" />
            </TabsTrigger>
            <TabsTrigger
              value="chatbot"
              className="nav-item"
              aria-label="Chatbot"
            >
              <MessageSquare size={19} />
              Chatbot
              {entries.length > 0 && (
                <span className="nav-count">{entries.length}</span>
              )}
            </TabsTrigger>
            <TabsTrigger
              value="map"
              className="nav-item"
              aria-label="Concept map"
            >
              <Network size={19} />
              Concept map<span className="nav-count">6</span>
            </TabsTrigger>
            <TabsTrigger
              value="activity"
              className="nav-item"
              aria-label="Session activity"
            >
              <History size={19} />
              Session activity
              {entries.length > 0 && (
                <span className="nav-count">{entries.length}</span>
              )}
            </TabsTrigger>
          </TabsList>
          <div className="rail-bottom">
            <div className="rail-note">
              <GitBranch size={20} />
              <p>
                Small steps.
                <br />
                <strong>Clearer connections.</strong>
              </p>
            </div>
            <div className="demo-label">
              <span />
              Deterministic demo
            </div>
            <p className="rail-footnote">Two questions. No live AI.</p>
          </div>
        </aside>
        <div className="app-main">
          <header className="topbar">
            <div className="breadcrumbs">
              <span>Introduction to AI</span>
              <ChevronRight size={14} />
              <strong>Search & heuristics</strong>
            </div>
            <div className="flex items-center gap-1 sm:gap-3">
              {onEditSetup && (
                <Button
                  variant="ghost"
                  onClick={onEditSetup}
                  className="text-muted-foreground"
                >
                  Course setup
                </Button>
              )}
              <Button
                variant="ghost"
                onClick={() => void newSession()}
                disabled={busy}
              >
                <RotateCcw size={15} />
                <span>New session / reset</span>
              </Button>
            </div>
          </header>
          <main id="workspace" className="workspace" tabIndex={-1}>
            <div className="page-heading">
              <div>
                <p className="eyebrow">THE LEARNING LAB</p>
                <h1>
                  {view === "study"
                    ? "Make the connection."
                    : view === "chatbot"
                      ? "Chatbot"
                      : view === "map"
                        ? "See the bigger picture."
                        : "Follow your thinking."}
                </h1>
                <p>
                  {view === "study"
                    ? "A little practice. A clearer understanding."
                    : view === "chatbot"
                      ? "Your study context, answers, and explanations together."
                      : view === "map"
                        ? "Six concepts, with room for uncertainty."
                        : "Your answers, feedback, and next steps in one place."}
                </p>
              </div>
              <div className="session-progress">
                <span className="progress-caption">
                  THIS SESSION{" "}
                  <strong>
                    {entries.length}
                    <span> / 2</span>
                  </strong>
                </span>
                <div
                  className="progress-segments"
                  aria-label={`${entries.length} of 2 questions answered`}
                >
                  <span className={entries.length > 0 ? "filled" : ""} />
                  <span className={entries.length > 1 ? "filled" : ""} />
                </div>
                <span className="progress-note">questions answered</span>
              </div>
            </div>
            {error && (
              <div className="error-banner" role="alert">
                <CircleHelp size={20} />
                <div>
                  <strong>Let’s get you back on track.</strong>
                  <p>
                    {error} Reset before continuing; your last visible results
                    are still here.
                  </p>
                </div>
                <Button
                  variant="secondary"
                  disabled={busy}
                  onClick={() => void newSession()}
                >
                  Try new session
                </Button>
              </div>
            )}
            <div className="desk-layout" data-view={view}>
              <div className="primary-column">
                <TabsContent
                  value="chatbot"
                  forceMount
                  hidden={view !== "chatbot"}
                  className="view-panel chatbot-page"
                >
                  <StudyChatbot
                    key={sessionId}
                    entries={entries}
                    question={question}
                    concepts={concepts}
                    preferences={preferences}
                    onPreferencesChange={setPreferences}
                    busy={busy}
                    error={error}
                  />
                  <Button
                    variant="ghost"
                    className="back-to-study"
                    onClick={() => setView("study")}
                  >
                    <ArrowLeft size={16} />
                    Back to study desk
                  </Button>
                </TabsContent>
                <TabsContent value="study" className="view-panel">
                  <div className="lesson-path" aria-label="Session sequence">
                    <span
                      className={
                        entries.length === 0 ||
                        (reviewing && entries.length === 1)
                          ? "current"
                          : "done"
                      }
                    >
                      <b>{entries.length ? <Check size={13} /> : "01"}</b>The
                      relationship
                    </span>
                    <span className="path-rule" />
                    <span
                      className={
                        entries.length > 0 && (!reviewing || entries.length > 1)
                          ? "current"
                          : ""
                      }
                    >
                      <b>{entries.length > 1 ? <Check size={13} /> : "02"}</b>A
                      fresh example
                    </span>
                  </div>
                  <section className="study-surface" aria-busy={busy}>
                    {!sessionId && busy ? (
                      <div className="loading-state" role="status">
                        <LoaderCircle className="spin" size={25} />
                        <h2>Setting up your study desk</h2>
                        <p>
                          Gathering the first question and concept estimates.
                        </p>
                      </div>
                    ) : !sessionId ? (
                      <div className="empty-state">
                        <CircleHelp size={28} />
                        <h2>Your desk is ready when you are.</h2>
                        <p>Start a session to load your first question.</p>
                        <Button
                          onClick={() => void newSession()}
                          disabled={busy}
                        >
                          Start session
                          <ArrowRight size={16} />
                        </Button>
                      </div>
                    ) : review ? (
                      <Scene key={`review-${entries.length}`}>
                        <div className="surface-meta">
                          <Outcome result={review.result} />
                          <span>REFLECTION {entries.length} / 2</span>
                        </div>
                        <h2
                          ref={focusHeading}
                          tabIndex={-1}
                          className="surface-title"
                        >
                          {complete
                            ? "One loop, a little more clarity."
                            : "Here’s the useful distinction."}
                        </h2>
                        <p className="assessment-feedback">
                          {review.result.assessment.feedback}
                        </p>
                        <Disclosure title="Review your answer">
                          <p>{review.question.prompt}</p>
                          <div className="submitted-answer">
                            <span>Your choice</span>
                            {
                              review.question.choices.find(
                                (choice) => choice.id === review.answer,
                              )?.text
                            }
                          </div>
                        </Disclosure>
                        <div className="tutor-handoff">
                          <MessageSquare size={23} aria-hidden="true" />
                          <div>
                            <h3>
                              {review.result.decision
                                ? activityNames[review.result.decision.kind]
                                : "Tutor reflection"}
                            </h3>
                            <p>Your explanation is ready in Chatbot.</p>
                          </div>
                          <Button variant="secondary" onClick={openChatbot}>
                            Read explanation
                            <ArrowRight size={16} />
                          </Button>
                        </div>
                        <div className="decision-strip">
                          <GitBranch size={19} />
                          <div>
                            <h3>
                              {complete ? "Why stop here?" : "Why this next?"}
                            </h3>
                            <p>
                              {review.result.decision?.reason ??
                                "You’ve reached the end of this two-question demo. Review the evidence or reset for another pass."}
                            </p>
                          </div>
                        </div>
                        <Trace result={review.result} />
                        <div className="surface-footer">
                          <span>
                            {complete
                              ? "Practice completed. Estimates remain experimental."
                              : "Apply the distinction to a different graph."}
                          </span>
                          <Button onClick={() => setReviewing(false)}>
                            {complete
                              ? "Session recap"
                              : "Try the next question"}
                            <ArrowRight size={17} />
                          </Button>
                        </div>
                      </Scene>
                    ) : question ? (
                      <Scene key={question.question_id}>
                        <div className="surface-meta">
                          <span>
                            <span className="tiny-dot" />
                            {entries.length
                              ? "TRANSFER PRACTICE"
                              : "QUICK CHECK"}
                          </span>
                          <span>QUESTION {entries.length + 1} / 2</span>
                        </div>
                        <h2
                          className="surface-title"
                          ref={focusHeading}
                          tabIndex={-1}
                        >
                          {names[question.concept_id] ?? question.concept_id}
                        </h2>
                        <form onSubmit={submit}>
                          <fieldset disabled={busy || !!error}>
                            <legend className="question-prompt">
                              {question.prompt}
                            </legend>
                            <div className="answer-options">
                              {question.choices.map((choice, index) => (
                                <label
                                  key={choice.id}
                                  className={`answer-option ${answer === choice.id ? "selected" : ""}`}
                                >
                                  <input
                                    type="radio"
                                    name="answer"
                                    value={choice.id}
                                    checked={answer === choice.id}
                                    onChange={() => setAnswer(choice.id)}
                                  />
                                  <span
                                    className="answer-letter"
                                    aria-hidden="true"
                                  >
                                    {choice.id === "unsure"
                                      ? "?"
                                      : String.fromCharCode(65 + index)}
                                  </span>
                                  <span>{choice.text}</span>
                                  <span
                                    className="answer-indicator"
                                    aria-hidden="true"
                                  >
                                    {answer === choice.id && (
                                      <Check size={12} strokeWidth={3} />
                                    )}
                                  </span>
                                </label>
                              ))}
                            </div>
                          </fieldset>
                          <div className="surface-footer">
                            <span>
                              <CircleHelp size={15} />
                              Take your time. It’s okay to be unsure.
                            </span>
                            <Button
                              type="submit"
                              disabled={!answer || busy || !!error}
                            >
                              {busy ? (
                                <>
                                  <LoaderCircle size={16} className="spin" />
                                  Checking answer
                                </>
                              ) : (
                                <>
                                  Check answer
                                  <ArrowRight size={17} />
                                </>
                              )}
                            </Button>
                          </div>
                        </form>
                        {latest && (
                          <button
                            className="text-button review-link"
                            onClick={() => setReviewing(true)}
                          >
                            <ArrowLeft size={14} />
                            Revisit the explanation
                          </button>
                        )}
                      </Scene>
                    ) : (
                      <Scene className="completion">
                        <span className="completion-symbol">
                          <CheckCheck size={28} />
                        </span>
                        <p className="eyebrow">SESSION COMPLETE</p>
                        <h2 ref={focusHeading} tabIndex={-1}>
                          A connection worth keeping.
                        </h2>
                        <p>
                          You worked through the relationship and a fresh
                          example. Explore what changed, or try the same loop
                          with a different explanation style.
                        </p>
                        <div className="recap-line">
                          <strong>{entries.length}</strong>
                          <span>questions answered</span>
                          <strong>
                            {concepts.find((c) => c.concept_id === focusConcept)
                              ?.evidence_count ?? 0}
                          </strong>
                          <span>accepted observations</span>
                        </div>
                        {entries[0] && (
                          <EvidenceComparison
                            before={entries[0].before}
                            after={concepts}
                          />
                        )}
                        <div className="completion-actions">
                          <Button onClick={() => setView("map")}>
                            Explore concept map
                            <ArrowRight size={16} />
                          </Button>
                          <Button
                            variant="secondary"
                            onClick={() => void newSession()}
                            disabled={busy}
                          >
                            <RotateCcw size={16} />
                            Practice again
                          </Button>
                        </div>
                        <p className="subtle">
                          Completion records practice, not proven mastery.
                        </p>
                      </Scene>
                    )}
                  </section>
                  <div className="learning-note">
                    <span className="note-line" />
                    <div>
                      <h3>
                        {entries.length
                          ? "Notice the evidence, not just the score."
                          : "Every answer has a next step."}
                      </h3>
                      <p>
                        {entries.length
                          ? "An estimate can move down as well as up. The interval shows how much is still uncertain."
                          : "Your response shapes the feedback, the concept estimate, and the next activity."}
                      </p>
                    </div>
                    <Layers3 size={28} strokeWidth={1.3} />
                  </div>
                </TabsContent>
                <TabsContent value="map" className="view-panel">
                  <section className="map-surface">
                    <div className="map-header">
                      <div>
                        <p className="eyebrow">CONCEPT MAP</p>
                        <h2>Search & heuristics</h2>
                      </div>
                      <span className="map-key">
                        <span className="tiny-dot" />
                        Current practice
                      </span>
                    </div>
                    <p className="map-help">
                      Select a concept to inspect its estimate. Connections
                      group topics; they do not imply mastery or prerequisites.
                    </p>
                    <div className="concept-map">
                      <div className="map-root">
                        <Network size={19} />
                        Graph search
                      </div>
                      <div className="map-branches">
                        {groups.map((group) => (
                          <div className="map-group" key={group.name}>
                            <h3>{group.name}</h3>
                            <div className="map-node-list">
                              {group.ids.map((id) => {
                                const concept = concepts.find(
                                  (c) => c.concept_id === id,
                                );
                                return (
                                  <button
                                    key={id}
                                    className={`map-node ${id === selectedConcept ? "is-selected" : ""}`}
                                    aria-pressed={id === selectedConcept}
                                    onClick={() => setSelectedConcept(id)}
                                  >
                                    <span className="map-node-title">
                                      {shortNames[id]}
                                      {id === focusConcept && (
                                        <span className="tiny-dot" />
                                      )}
                                    </span>
                                    <span>
                                      {concept?.evidence_count
                                        ? pct(concept.mean)
                                        : "—"}
                                      <small>
                                        {concept?.evidence_count
                                          ? `${concept.evidence_count} observations`
                                          : "No evidence yet"}
                                      </small>
                                    </span>
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                    {selected && (
                      <div className="map-selection" key={selectedConcept}>
                        <div>
                          <span className="eyebrow">SELECTED CONCEPT</span>
                          <h3>{names[selectedConcept]}</h3>
                          <p>
                            {selected.evidence_count
                              ? `${selected.evidence_count} accepted observations in this session.`
                              : "No answers have supplied evidence for this concept yet."}
                          </p>
                        </div>
                        <div className="map-selection-value">
                          <strong>{pct(selected.mean)}</strong>
                          <span>mastery estimate</span>
                        </div>
                      </div>
                    )}
                    <div className="map-footer">
                      <Info size={16} />
                      <p>
                        Estimates use Bayesian updates. A 50% starting
                        estimate with no evidence does not mean you know half
                        the material.
                      </p>
                    </div>
                    {entries.some(
                      (entry) => entry.question.concept_id === selectedConcept,
                    ) && (
                      <section
                        className="concept-answer-history"
                        aria-label="Answers for this concept"
                      >
                        <h3>Responses for this concept</h3>
                        <ol>
                          {entries
                            .filter(
                              (entry) =>
                                entry.question.concept_id === selectedConcept,
                            )
                            .map((entry, index) => (
                              <li key={entry.question.question_id}>
                                <small>
                                  Response {index + 1} ·{" "}
                                  {entry.result.assessment.outcome}
                                </small>
                                <p>{entry.result.assessment.feedback}</p>
                                <Disclosure
                                  title={`Review response ${index + 1}`}
                                >
                                  <p>{entry.question.prompt}</p>
                                  <p>
                                    Your choice:{" "}
                                    {entry.question.choices.find(
                                      (choice) => choice.id === entry.answer,
                                    )?.text ?? entry.answer}
                                  </p>
                                  <p>{entry.result.tutor.text}</p>
                                </Disclosure>
                              </li>
                            ))}
                        </ol>
                      </section>
                    )}
                  </section>
                  <Button
                    variant="ghost"
                    className="back-to-study"
                    onClick={() => setView("study")}
                  >
                    <ArrowLeft size={15} />
                    Back to your study desk
                  </Button>
                </TabsContent>
                <TabsContent value="activity" className="view-panel">
                  <section className="activity-surface">
                    <div className="map-header">
                      <div>
                        <p className="eyebrow">SESSION JOURNAL</p>
                        <h2>The path so far</h2>
                      </div>
                      <span className="tag">{entries.length} responses</span>
                    </div>
                    {entries.length ? (
                      <ol className="activity-list">
                        {entries.map((entry, i) => (
                          <li key={`${entry.question.question_id}-${i}`}>
                            <span className="activity-number">0{i + 1}</span>
                            <div>
                              <div className="activity-title">
                                <h3>
                                  {i === 0
                                    ? "The relationship"
                                    : "A fresh example"}
                                </h3>
                                <Outcome result={entry.result} />
                              </div>
                              <p>
                                {
                                  entry.question.choices.find(
                                    (c) => c.id === entry.answer,
                                  )?.text
                                }
                              </p>
                              <p className="journal-feedback">
                                {entry.result.assessment.feedback}
                              </p>
                              <Disclosure title="Read the tutor response">
                                <div className="tutor-text">
                                  {entry.result.tutor.text}
                                </div>
                                <p className="subtle">
                                  {entry.result.decision?.reason ??
                                    "Two-question demo complete."}
                                </p>
                              </Disclosure>
                              <Trace result={entry.result} />
                            </div>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <div className="empty-state">
                        <History size={32} strokeWidth={1.4} />
                        <h3>Your thinking starts here.</h3>
                        <p>
                          Answer your first question to see feedback and the
                          steps behind it.
                        </p>
                        <Button onClick={() => setView("study")}>
                          Go to first question
                          <ArrowRight size={16} />
                        </Button>
                      </div>
                    )}
                    <div className="journal-note">
                      <Terminal size={15} />
                      This journal lasts for the current session. Reset clears
                      it.
                    </div>
                  </section>
                </TabsContent>
              </div>
              <aside
                className="inspector"
                hidden={view === "chatbot"}
                aria-label="Concept estimates and teaching preferences"
              >
                <section className="knowledge-panel">
                  <div className="inspector-heading">
                    <h2>Your understanding</h2>
                    <span className="tag">6 concepts</span>
                  </div>
                  <p className="inspector-description">
                    Mastery estimates, with uncertainty.
                  </p>
                  <div className="concept-list">
                    {concepts.length ? (
                      concepts.map((concept) => (
                        <button
                          key={concept.concept_id}
                          className={`concept-row ${selectedConcept === concept.concept_id ? "is-selected" : ""}`}
                          onClick={() => setSelectedConcept(concept.concept_id)}
                          aria-pressed={selectedConcept === concept.concept_id}
                        >
                          <span className="concept-row-title">
                            {names[concept.concept_id]}
                            {concept.concept_id === focusConcept && (
                              <span className="concept-practice-label">
                                Practicing
                              </span>
                            )}
                          </span>
                          <strong>
                            {concept.evidence_count
                              ? pct(concept.mean)
                              : "No evidence"}
                          </strong>
                        </button>
                      ))
                    ) : (
                      <div className="concept-loading" role="status">
                        Waiting for concept estimates…
                      </div>
                    )}
                  </div>
                  {selected && (
                    <div className="concept-detail" key={selected.concept_id}>
                      <div className="detail-heading">
                        <span>{shortNames[selected.concept_id]}</span>
                        <span>
                          {selected.evidence_count}{" "}
                          {selected.evidence_count === 1
                            ? "observation"
                            : "observations"}
                        </span>
                      </div>
                      <Estimate concept={selected} />
                      <p>
                        {selected.evidence_count === 0
                          ? "A starting estimate. We need evidence to learn more."
                          : "Only accepted answers on this concept supply evidence."}
                      </p>
                    </div>
                  )}
                  <Disclosure title="How to read these estimates">
                    <p>
                      Experimental predicted success on similar unaided
                      questions. The marker is the estimate; the shaded range is
                      its 90% interval.
                    </p>
                    <p>
                      Bayesian estimates update from accepted answer evidence.
                      Explanations alone never increase an estimate.
                    </p>
                  </Disclosure>
                </section>
                <TeachingPreferences
                  preferences={preferences}
                  onChange={setPreferences}
                  busy={busy}
                />
                <div className="inspector-footnote">
                  <Info size={14} />
                  <span>Practice space. Not a grade.</span>
                </div>
              </aside>
            </div>
            <footer className="page-footer">
              <span>
                MINDS & MACHINES <span className="footer-divider">/</span>{" "}
                LEARNING LAB
              </span>
              <span>Deterministic demo · no live AI</span>
            </footer>
          </main>
        </div>
        <span className="sr-only" role="status">
          {busy
            ? "Loading, please wait."
            : reviewing && latest
              ? `Answer ${entries.length}: ${latest.result.assessment.outcome}. Feedback is ready.`
              : ""}
        </span>
      </Tabs>
    </MotionConfig>
  );
}
