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
  House,
  Info,
  Layers3,
  LoaderCircle,
  MessageSquare,
  Network,
  FolderOpen,
  RotateCcw,
  Terminal,
  Waypoints,
} from "lucide-react";
import type {
  CoachContext,
  SessionResponse,
  PracticeCounts,
  ConceptEstimate,
  Flashcard,
  LearnerPresentationPreferences,
  PublicQuestion,
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
import { post, requestErrorMessage } from "./lib/api";
import { createSession, CourseError } from "./lib/courses";
import { CourseBoundary, useCourseLabels } from "./components/course/CourseContext";
import { FocusRanking } from "./components/study/FocusRanking";
import { BetaDistributionPlot } from "./components/study/BetaDistributionPlot";
import { AnswerImpact, AnswerModelDetails, NextStep, teachingPreview } from "./components/study/AnswerImpact";
import { Flashcards } from "./components/study/Flashcards";
import {
  TeachingSource,
  teachingLabel,
} from "./components/study/TeachingSource";
import { StudyChatbot } from "./components/study/StudyChatbot";
import { StudyOverview } from "./components/study/StudyOverview";
import { MaterialsWorkspace } from "./components/study/MaterialsWorkspace";
import { initialDraft, type CourseDraft } from "./components/onboarding/model";
import { EvidenceComparison } from "./components/study/EvidenceComparison";
import { TeachingPreferences } from "./components/study/TeachingPreferences";
import {
  intervalWidth,
  type StudyEntry,
} from "./components/study/model";

const demoShortNames: Record<string, string> = {
  bfs: "BFS",
  ucs: "UCS",
  astar: "A*",
  admissibility: "Admissibility",
  consistency: "Consistency",
  admissibility_vs_consistency: "The connection",
};
const stages: Record<string, string> = {
  assess: "Assessment",
  update: "Concept estimate",
  select: "Next activity",
  teach: "Teaching response",
};
const demoGroups = [
  { name: "Search strategies", ids: ["bfs", "ucs", "astar"] },
  {
    name: "Heuristic properties",
    ids: ["admissibility", "consistency", "admissibility_vs_consistency"],
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
        {teachingLabel(result)}. Returned mode: {result.mode}; provider:{" "}
        {result.provider}. These are the stages reported by the API, not proof
        of live AI generation.
      </p>
      <ol className="trace-list">
        {result.trace.map((stage, index) => (
          <li key={`${stage}-${index}`}>
            <Check size={14} aria-hidden="true" />
            <span>
              {stages[stage] ?? stage}
              <small>{stage}</small>
            </span>
          </li>
        ))}
      </ol>
    </Disclosure>
  );
}

type AppProps = {
  onEditSetup?: () => void;
  course?: { draft: CourseDraft; onChange: (draft: CourseDraft) => void };
};
export function App(props: AppProps = {}) {
  return <CourseBoundary><CourseWorkspace {...props} /></CourseBoundary>;
}
function CourseWorkspace(props: AppProps) {
  const { course } = useCourseLabels();
  const [preferences, setPreferences] = useState(defaults);
  const [localDraft, setLocalDraft] = useState(initialDraft);
  // A new course has a fresh UI lifetime: answers, chat, evidence and pending
  // responses from the previous course cannot leak into it. Preferences survive.
  return <LearningWorkspace key={course ? `course:${course.course_id}` : "demo"} {...props}
    course={props.course ?? { draft: localDraft, onChange: setLocalDraft }}
    preferences={preferences} setPreferences={setPreferences} />;
}
function LearningWorkspace({ onEditSetup, course, preferences, setPreferences }: AppProps & {
  course: NonNullable<AppProps["course"]>;
  preferences: LearnerPresentationPreferences;
  setPreferences: (value: LearnerPresentationPreferences) => void;
}) {
  const { course: activeCourse, title: courseTitle, names } = useCourseLabels();
  const shortNames = activeCourse ? names : demoShortNames;
  const courseDraft = course.draft;
  const changeCourse = course.onChange;
  const [analytics, setAnalytics] = useState<CoachContext>();
  const [focusId, setFocusId] = useState<string | null>(null);
  const [practiceNotice, setPracticeNotice] = useState("");
  const [counts, setCounts] = useState<PracticeCounts | null>(null);
  const [sessionStart, setSessionStart] = useState<ConceptEstimate[]>([]);
  const [confirmReset, setConfirmReset] = useState(false);
  const [sessionId, setSessionId] = useState("");
  const [question, setQuestion] = useState<PublicQuestion | null>(null);
  const [concepts, setConcepts] = useState<ConceptEstimate[]>([]);
  const [entries, setEntries] = useState<StudyEntry[]>([]);
  const [questionCount, setQuestionCount] = useState<number | null>(null);
  const [flashcards, setFlashcards] = useState<Flashcard[]>([]);
  const [studyMode, setStudyMode] = useState<"practice" | "flashcards">("practice");
  const [answer, setAnswer] = useState("");
  const [requestBusy, setBusy] = useState(true);
  const [chatBusy, setChatBusy] = useState(false);
  const busy = requestBusy || chatBusy;
  const [error, setError] = useState("");
  const [view, setView] = useState("study");
  const [orientation, setOrientation] = useState<"vertical" | "horizontal">(
    "vertical",
  );
  const [reviewing, setReviewing] = useState(false);
  const [selectedConcept, setSelectedConcept] = useState("");
  const requestInFlight = useRef(false);
  const focusHeading = useRef<HTMLHeadingElement>(null);
  const latest = entries.at(-1);
  const focusConcept = (reviewing ? latest?.question.concept_id : question?.concept_id) ?? latest?.question.concept_id ?? "";
  const groups = activeCourse
    ? [{ name: "Course concepts", ids: concepts.map(c => c.concept_id) }]
    : demoGroups.map(group => ({ ...group, ids: group.ids.filter(id => concepts.some(c => c.concept_id === id)) }));
  const selected = concepts.find(
    (concept) => concept.concept_id === selectedConcept,
  );
  const complete = !!sessionId && !question;
  const review = reviewing ? latest : undefined;
  const feedbackVisible = view === "study" && studyMode === "practice" && reviewing;

  async function newSession(resetLearner = false, targetConcept?: string) {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const result = targetConcept
        ? await post<SessionResponse>("focus-practice", { session_id: sessionId, concept_id: targetConcept })
        : await createSession(activeCourse, sessionId || undefined, resetLearner);
      setAnalytics(result.analytics);
      setFocusId(result.focus_concept_id ?? null);
      setPracticeNotice(result.practice_notice ?? "");
      setCounts(result.counts ?? null);
      setSessionStart(result.session_start?.length ? result.session_start : result.concepts);
      setConfirmReset(false);
      setSessionId(result.session_id);
      setQuestion(result.question);
      setConcepts(result.concepts);
      setEntries([]);
      setQuestionCount(result.question_count || activeCourse?.question_count || null);
      setFlashcards(result.flashcards ?? []);
      setStudyMode("practice");
      setAnswer("");
      setReviewing(false);
      setView("study");
      setSelectedConcept(result.question.concept_id);
    } catch (err) {
      setError(
        err instanceof CourseError ? err.message : requestErrorMessage(err),
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
    if (sessionId) focusHeading.current?.focus({ preventScroll: true });
  }, [sessionId]);
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
    if (view === "study" && studyMode === "practice" && entries.length)
      focusHeading.current?.focus({ preventScroll: true });
  }, [reviewing, entries.length, view, studyMode]);

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
      const allowed = new Set(concepts.map(c => c.concept_id));
      if (result.session_id !== sessionId || result.concepts.length !== allowed.size ||
          new Set(result.concepts.map(c => c.concept_id)).size !== allowed.size ||
          result.concepts.some(c => !allowed.has(c.concept_id)) ||
          (result.next_question && !allowed.has(result.next_question.concept_id)) ||
          (result.decision && !allowed.has(result.decision.concept_id))) {
        throw new Error("Mismatched course response");
      }
      setEntries((previous) => [
        ...previous,
        { question, answer, result, before: concepts },
      ]);
      setCounts(result.counts ?? null);
      setConcepts(result.concepts);
      setAnalytics(result.analytics);
      setQuestion(result.next_question);
      if (result.flashcards) setFlashcards(result.flashcards);
      setAnswer("");
      setReviewing(true);
      setSelectedConcept(question.concept_id);
    } catch (err) {
      setError(
        requestErrorMessage(err),
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

  const inspector = <>
    <section className="knowledge-panel">
      <div className="inspector-heading">
        <h2>Your understanding</h2>
        <span className="tag">{concepts.length} concepts</span>
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
                {names[concept.concept_id] ?? concept.concept_id}
                {!complete && concept.concept_id === focusConcept && (
                  <span className="concept-practice-label">
                    Practicing
                  </span>
                )}
              </span>
              <BetaDistributionPlot current={concept} compact />
              <small>{concept.evidence_count} observations</small>
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
            <span>{shortNames[selected.concept_id] ?? selected.concept_id}</span>
            <span>
              {selected.evidence_count}{" "}
              {selected.evidence_count === 1
                ? "observation"
                : "observations"}
            </span>
          </div>
          <p className="detail-estimate">
            Understanding estimate:{" "}
            <strong>{pct(selected.mean)}</strong>
          </p>
          <BetaDistributionPlot current={selected} />
          <Estimate concept={selected} />
          <p>
            {selected.evidence_count === 0
              ? "A starting estimate. We need evidence to learn more."
              : "Only accepted answers on this concept supply evidence."}
          </p>
        </div>
      )}
      <Button variant="ghost" disabled={busy} onClick={() => setConfirmReset(true)}>Reset learner profile</Button>
      {confirmReset && <div role="group" aria-label="Confirm learner reset">
        <p>Erase accumulated evidence and return every concept to its starting distribution?</p>
        <Button disabled={busy} onClick={() => void newSession(true)}>Erase evidence and restart</Button>
        <Button variant="ghost" onClick={() => setConfirmReset(false)}>Keep my evidence</Button>
      </div>}
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
  </>;

  return (
    <MotionConfig reducedMotion="user">
      <Tabs
        value={view}
        onValueChange={setView}
        className="app-shell workspace-with-chat soft-workspace"
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
              {courseTitle}<small>{activeCourse ? "Uploaded course" : "Search & heuristics"}</small>
            </span>
          </div>
          <TabsList className="navigation-list" aria-label="Learning workspace">
            <TabsTrigger
              value="overview"
              className="nav-item"
              aria-label="Home"
            >
              <House size={19} />
              Home
            </TabsTrigger>
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
              Concept map<span className="nav-count">{concepts.length}</span>
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
            <TabsTrigger
              value="materials"
              className="nav-item"
              aria-label="Materials"
            >
              <FolderOpen size={19} />
              Materials
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
              {activeCourse ? "Uploaded course session" : "Adaptive learning demo"}
            </div>
            <p className="rail-footnote">Teaching source shown per response.</p>
          </div>
        </aside>
        <div className="app-main">
          <header className="topbar">
            <div className="breadcrumbs">
              <span>{courseTitle}</span>
              <ChevronRight size={14} />
              <strong>{activeCourse ? "Course practice" : "Search & heuristics"}</strong>
            </div>
            <div className="flex min-w-0 flex-wrap items-center gap-1 sm:gap-3">
              {onEditSetup && (
                <Button
                  variant="ghost"
                  onClick={onEditSetup}
                  className="px-2 text-muted-foreground sm:px-4"
                >
                  Course setup
                </Button>
              )}
              <Button
                variant="ghost"
                onClick={() => void newSession()}
                disabled={busy}
                className="px-2 sm:px-4"
              >
                <RotateCcw size={15} />
                <span>New practice session</span>
              </Button>
            </div>
          </header>
          <main id="workspace" className="workspace" tabIndex={-1}>
            <div className="page-heading">
              <div>
                <p className="eyebrow">THE LEARNING LAB</p>
                <h1>
                  {view === "overview"
                    ? "A little progress starts here."
                    : view === "study"
                      ? "Make the connection."
                      : view === "chatbot"
                        ? "Chatbot"
                        : view === "map"
                          ? "See the bigger picture."
                          : view === "materials"
                            ? "Your course, in one place."
                            : "Follow your thinking."}
                </h1>
                <p>
                  {view === "overview"
                    ? "Your understanding, your evidence, and a clear next step."
                    : view === "study"
                      ? "A little practice. A clearer understanding."
                      : view === "chatbot"
                        ? "Your study context, answers, and explanations together."
                        : view === "map"
                          ? `${concepts.length} concepts, with room for uncertainty.`
                          : view === "materials"
                            ? "Keep your notes and study goals close at hand."
                            : "Your answers, feedback, and next steps in one place."}
                </p>
              </div>
              {view !== "materials" && (
                <div className="session-progress">
                  <span className="progress-caption">
                    THIS SESSION{" "}
                    <strong>
                      {entries.length}
                      {questionCount !== null && <span> / {questionCount}</span>}
                    </strong>
                  </span>
                  <div
                    className="progress-segments"
                    aria-label={`${entries.length} questions answered`}
                  >
                    {Array.from({ length: questionCount ?? Math.max(1, entries.length) }, (_, index) =>
                      <span key={index} className={entries.length > index ? "filled" : ""} />)}
                  </div>
                  <span className="progress-note">questions answered</span>
                </div>
              )}
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
            <div className="desk-layout" data-view={view} data-feedback={feedbackVisible}>
              <div className="primary-column">
                <TabsContent
                  value="overview"
                  className="view-panel overview-page"
                >
                  <StudyOverview
                    concepts={concepts}
                    question={question}
                    entries={entries}
                    draft={courseDraft}
                    busy={busy}
                    error={error}
                    onStudy={() => setView("study")}
                    onConcept={(id) => {
                      setSelectedConcept(id);
                      setView("map");
                    }}
                    onMaterials={() => setView("materials")}
                  />
                </TabsContent>
                <TabsContent
                  value="materials"
                  className="view-panel materials-page"
                >
                  <MaterialsWorkspace
                    draft={courseDraft}
                    onChange={changeCourse}
                  />
                </TabsContent>
                <TabsContent
                  value="chatbot"
                  forceMount
                  hidden={view !== "chatbot"}
                  className="view-panel chatbot-page"
                >
                  <StudyChatbot
                    analytics={analytics}
                    onPractice={activeCourse ? (id) => void newSession(false, id) : undefined}
                    key={sessionId}
                    sessionId={sessionId}
                    onBusyChange={value => { requestInFlight.current = value; setChatBusy(value); }}
                    entries={entries}
                    question={question}
                    concepts={concepts}
                    preferences={preferences}
                    onPreferencesChange={setPreferences}
                    busy={busy}
                    error={error}
                    onManageMaterials={() => setView("materials")}
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
                <TabsContent value="study" className="view-panel" forceMount hidden={view !== "study"}>
                  <div className="study-mode" role="group" aria-label="Study mode">
                    <Button variant="ghost" aria-pressed={studyMode === "practice"} onClick={() => setStudyMode("practice")}><BookOpen size={16} />Practice quiz</Button>
                    <Button variant="ghost" aria-pressed={studyMode === "flashcards"} onClick={() => setStudyMode("flashcards")}><Layers3 size={16} />Flashcards</Button>
                  </div>
                  <div hidden={studyMode !== "flashcards"}><Flashcards key={sessionId} cards={flashcards} names={names} /></div>
                  <div hidden={studyMode !== "practice"}>
                  {view === "study" && <>
                  <div className="lesson-path" aria-label="Session sequence">
                    <span
                      className={reviewing ? "done" : "current"}
                    >
                      <b><BookOpen size={13} /></b>{focusId ? "Focus practice · " : ""}{complete ? "Practice complete" : `Question ${Math.max(1, entries.length + (reviewing ? 0 : 1))}${questionCount ? ` of ${questionCount}` : ""}`}
                    </span>
                    <span className="path-rule" />
                    <span
                      className={reviewing ? "current" : ""}
                    >
                      <b><Check size={13} /></b>Review & reflect
                    </span>
                  </div>
                  {practiceNotice && <p role="status">{practiceNotice}</p>}
                  {focusId && !reviewing && (() => {
                    const current = concepts.find(c => c.concept_id === focusId);
                    const before = sessionStart.find(c => c.concept_id === focusId);
                    return current && before ? <section className="focus-progress" aria-label="Focus practice progress">
                      <h3>{shortNames[focusId]} · continuing your learner model</h3>
                      <BetaDistributionPlot current={current} before={before} />
                      <p>{pct(before.mean)} → {pct(current.mean)} estimate · {current.evidence_count - before.evidence_count} observations added</p>
                      <p>90% interval width: {pct(before.interval90.upper - before.interval90.lower)} → {pct(current.interval90.upper - current.interval90.lower)}</p>
                    </section> : null;
                  })()}
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
                          <span>FEEDBACK {entries.length}</span>
                          <TeachingSource result={review.result} />
                        </div>
                        <h2 ref={focusHeading} tabIndex={-1} className="surface-title feedback-title">
                          {review.result.assessment.outcome === "correct" ? "Correct — nicely done."
                            : review.result.assessment.outcome === "incorrect" ? "Not quite — let’s unpack it."
                            : "Not sure yet? Let’s work through it."}
                        </h2>
                        <p className="feedback-explanation">{teachingPreview(review.result.tutor.text)}</p>
                        <Button variant="ghost" onClick={openChatbot} className="feedback-explanation-link">
                          <MessageSquare size={16} />Read explanation<ArrowRight size={15} />
                        </Button>
                        <AnswerImpact entry={review} />
                        <div className="surface-footer feedback-footer">
                          <NextStep entry={review} />
                          <Button onClick={() => { setReviewing(false); if (question) setSelectedConcept(question.concept_id); }}>
                            {complete ? "Session recap" : "Continue"}<ArrowRight size={17} />
                          </Button>
                        </div>
                        <Disclosure title="See model details">
                          <AnswerModelDetails entry={review} />
                          <h3>Your answer</h3>
                          <p>{review.question.prompt}</p>
                          <p>{review.question.choices.find(choice => choice.id === review.answer)?.text ?? review.answer}</p>
                          {focusId && <p>Focus practice continues your existing learner model. The recap compares session start with current evidence.</p>}
                          <Trace result={review.result} />
                          {inspector}
                        </Disclosure>
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
                          <span>QUESTION {entries.length + 1}</span>
                        </div>
                        <h2
                          className="surface-title"
                          ref={focusHeading}
                          tabIndex={-1}
                        >
                          {names[question.concept_id] ?? question.concept_id}
                        </h2>
                        {question.review && <p className="review-notice">Review item · Seen before. This answer will not add mastery evidence.</p>}
                        <form onSubmit={submit}>
                          <fieldset disabled={busy || !!error} data-question-id={question.question_id}
                            data-concept-id={question.concept_id}>
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
                                  {chatBusy ? "Tutor replying" : "Checking answer"}
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
                            onClick={() => { setReviewing(true); if (latest) setSelectedConcept(latest.question.concept_id); }}
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
                          Review your course practice and what changed, or start
                          a new session with a different explanation style.
                        </p>
                        <div className="recap-line">
                          <strong>{entries.length}</strong>
                          <span>questions answered</span>
                          <strong>
                            {counts?.accepted_observations ?? concepts.reduce((count, c) => count + c.evidence_count, 0) - sessionStart.reduce((count, c) => count + c.evidence_count, 0)}
                          </strong>
                          <span>accepted observations this session</span>
                          <strong>{counts?.unique_questions_seen ?? new Set(entries.map(e => e.question.question_id)).size}</strong>
                          <span>unique questions seen</span>
                        </div>
                        {counts && <p>{counts.review_attempts ?? 0} review attempts · {counts.focus_observations ?? 0} focus observations this session · {counts.lifetime_evidence ?? concepts.reduce((n, c) => n + c.evidence_count, 0)} lifetime observations</p>}
                        {entries[0] && (
                          <EvidenceComparison
                            before={sessionStart}
                            after={concepts}
                          />
                        )}
                        <FocusRanking analytics={analytics} busy={busy}
                          onPractice={activeCourse ? (id) => void newSession(false, id) : undefined} />
                        <div className="completion-actions">
                          <Button onClick={openChatbot}>Discuss my results</Button>
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
                          Practice again carries your understanding model forward. Completion records practice, not proven mastery.
                        </p>
                      </Scene>
                    )}
                  </section>
                  <div className="learning-note" hidden={reviewing}>
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
                  </>}
                  </div>
                </TabsContent>
                <TabsContent value="map" className="view-panel">
                  <section className="map-surface">
                    <div className="map-header">
                      <div>
                        <p className="eyebrow">CONCEPT MAP</p>
                        <h2>{activeCourse ? courseTitle : "Search & heuristics"}</h2>
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
                        {activeCourse ? courseTitle : "Graph search"}
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
                                      {shortNames[id] ?? names[id] ?? id}
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
                      <section
                        className="map-evidence"
                        aria-label="Selected concept evidence"
                        key={selectedConcept}
                      >
                        <div className="map-selection">
                          <div>
                            <span className="eyebrow">SELECTED CONCEPT</span>
                            <h3>{names[selectedConcept] ?? selectedConcept}</h3>
                            <p>
                              {selected.evidence_count
                                ? `${selected.evidence_count} accepted observations across practice sessions.`
                                : "No answers have supplied evidence for this concept yet."}
                            </p>
                          </div>
                          <div className="map-selection-value">
                            <strong>{pct(selected.mean)}</strong>
                            <span>understanding estimate</span>
                          </div>
                        </div>
                        <dl className="concept-evidence-values">
                          <div>
                            <dt>90% uncertainty range</dt>
                            <dd>
                              {pct(selected.interval90.lower)} –{" "}
                              {pct(selected.interval90.upper)}
                            </dd>
                          </div>
                          <div>
                            <dt>Interval width</dt>
                            <dd>{intervalWidth(selected)} percentage points</dd>
                          </div>
                        </dl>
                        <p className="impact-note">
                          Experimental predicted success on comparable unaided
                          questions.{" "}
                          {selected.evidence_count === 0 &&
                            "No evidence yet; this is a starting estimate, not a grade."}
                        </p>
                        {!entries.some(
                          (entry) =>
                            entry.question.concept_id === selectedConcept,
                        ) && (
                          <p className="impact-note">
                            No responses for this concept in this session.
                          </p>
                        )}
                      </section>
                    )}
                    <div className="map-footer">
                      <Info size={16} />
                      <p>
                        Estimates use Bayesian updates. A 50% starting estimate
                        with no evidence does not mean you know half the
                        material.
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
                                  <TeachingSource result={entry.result} />
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
                                <TeachingSource result={entry.result} />
                                <div className="tutor-text">
                                  {entry.result.tutor.text}
                                </div>
                                <p className="subtle">
                                  {entry.result.decision?.reason ??
                                    "Demo complete."}
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
                hidden={
                  view === "overview" ||
                  view === "chatbot" ||
                  view === "materials" ||
                  feedbackVisible
                }
                aria-label="Concept estimates and teaching preferences"
              >
                {!feedbackVisible && inspector}
              </aside>
            </div>
            <footer className="page-footer">
              <span>
                MINDS & MACHINES <span className="footer-divider">/</span>{" "}
                LEARNING LAB
              </span>
              <span>Teaching source shown with each response</span>
            </footer>
          </main>
        </div>
        <span className="sr-only" role="status">
          {busy
            ? "Loading, please wait."
            : reviewing && latest
              ? `Answer ${entries.length}: ${latest.result.assessment.outcome}. ${teachingLabel(latest.result)}. Feedback and before/after evidence are ready.`
              : ""}
        </span>
      </Tabs>
    </MotionConfig>
  );
}
