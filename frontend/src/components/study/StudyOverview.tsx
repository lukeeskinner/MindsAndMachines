import {
  ArrowRight,
  BookOpen,
  CalendarDays,
  ChevronRight,
  Clock3,
  Focus,
  Sprout,
} from "lucide-react";
import type {
  ConceptEstimate,
  PublicQuestion,
} from "../../../../contracts/api";
import { formatDate, goals, type CourseDraft } from "../onboarding/model";
import { Button, Disclosure } from "../ui/primitives";
import { activityNames, conceptName, percent, type StudyEntry } from "./model";
import { TeachingSource } from "./TeachingSource";

type Props = {
  concepts: ConceptEstimate[];
  question: PublicQuestion | null;
  entries: StudyEntry[];
  draft: CourseDraft;
  busy: boolean;
  error: string;
  onStudy: () => void;
  onConcept: (id: string) => void;
  onMaterials: () => void;
};

export function StudyOverview({
  concepts,
  question,
  entries,
  draft,
  busy,
  error,
  onStudy,
  onConcept,
  onMaterials,
}: Props) {
  const latest = entries.at(-1);
  const focusId = latest?.question.concept_id ?? question?.concept_id;
  const focus = concepts.find((concept) => concept.concept_id === focusId);
  const decision = latest?.result.decision;
  const completed = !question && !!latest;
  return (
    <section
      className="study-overview"
      aria-label="Learning overview"
      aria-busy={busy}
    >
      <div className="overview-surface">
        <div className="overview-summary">
          <section
            className="overview-understanding"
            aria-labelledby="overview-understanding-title"
          >
            <div className="overview-section-label">
              <Focus size={17} aria-hidden="true" /> YOUR CURRENT FOCUS
            </div>
            <h2 id="overview-understanding-title">
              Understanding, with context.
            </h2>
            {focus ? (
              <>
                <p className="overview-focus-name">
                  {conceptName(focus.concept_id)}
                </p>
                <div className="overview-estimate">
                  <strong>{percent(focus.mean)}</strong>
                  <span>
                    understanding estimate
                    <small>
                      {focus.evidence_count === 0
                        ? "Starting estimate · no evidence yet"
                        : `${focus.evidence_count} ${focus.evidence_count === 1 ? "observation" : "observations"} recorded`}
                    </small>
                  </span>
                </div>
                <div className="overview-range" aria-hidden="true">
                  <span
                    style={{
                      left: percent(focus.interval90.lower),
                      width: percent(
                        focus.interval90.upper - focus.interval90.lower,
                      ),
                    }}
                  />
                  <i style={{ left: percent(focus.mean) }} />
                </div>
                <div className="overview-range-label">
                  <span>90% uncertainty range</span>
                  <strong>
                    {percent(focus.interval90.lower)} –{" "}
                    {percent(focus.interval90.upper)}
                  </strong>
                </div>
                <p className="overview-footnote">
                  Experimental predicted success on comparable unaided questions
                  for this concept.
                </p>
              </>
            ) : (
              <p className="overview-footnote" role="status">
                {error
                  ? "Your estimates could not be loaded. Try a new session."
                  : "Loading your first question and concept estimates…"}
              </p>
            )}
          </section>
          <section
            className="overview-plan"
            aria-labelledby="overview-plan-title"
          >
            <h2 id="overview-plan-title">Your study plan</h2>
            <p className="overview-plan-course">
              {draft.courseName.trim() || "Your course"}
            </p>
            <dl>
              <div>
                <dt>
                  <CalendarDays size={17} aria-hidden="true" />
                  {draft.goal === "exam" ? "Exam date" : "Target date"}
                </dt>
                <dd>{formatDate(draft.examDate)}</dd>
              </div>
              <div>
                <dt>
                  <Clock3 size={17} aria-hidden="true" />
                  Time you set aside
                </dt>
                <dd>
                  {draft.studyHours}{" "}
                  {draft.studyHours === "1" ? "hour" : "hours"} total
                </dd>
              </div>
              <div>
                <dt>Your goal</dt>
                <dd>{goals.find((goal) => goal.id === draft.goal)?.label}</dd>
              </div>
            </dl>
            <button className="overview-text-link" onClick={onMaterials}>
              Edit course & goals <ArrowRight size={15} aria-hidden="true" />
            </button>
            <p className="overview-footnote">
              Local setup only. Files and goals are not supplied to the tutor.
            </p>
          </section>
        </div>
        <div className="overview-detail">
          <section
            className="overview-concepts"
            aria-labelledby="overview-concepts-title"
          >
            <div className="overview-section-heading">
              <h2 id="overview-concepts-title">Your concept picture</h2>
              <span>{concepts.length} concepts</span>
            </div>
            <p className="overview-footnote">
              Select a concept to inspect its evidence.
            </p>
            <ul>
              {concepts.map((concept) => (
                <li key={concept.concept_id}>
                  <button onClick={() => onConcept(concept.concept_id)}>
                    <span
                      className={`overview-concept-dot ${concept.evidence_count > 0 ? "has-evidence" : ""}`}
                      aria-hidden="true"
                    />
                    <span className="overview-concept-name">
                      {conceptName(concept.concept_id)}
                      <small>
                        {concept.evidence_count === 0
                          ? "No evidence yet"
                          : `${concept.evidence_count} ${concept.evidence_count === 1 ? "observation" : "observations"}`}
                      </small>
                    </span>
                    <span className="overview-concept-value">
                      {concept.evidence_count === 0
                        ? "—"
                        : percent(concept.mean)}
                    </span>
                    <ChevronRight size={15} aria-hidden="true" />
                  </button>
                </li>
              ))}
            </ul>
          </section>
          <section
            className="overview-next"
            aria-labelledby="overview-next-title"
          >
            <div className="overview-section-label">
              <BookOpen size={17} aria-hidden="true" /> YOUR NEXT STEP
            </div>
            <h2 id="overview-next-title">
              {completed
                ? "Take a look back."
                : decision
                  ? activityNames[decision.kind]
                  : "Start with a question."}
            </h2>
            <p className="overview-next-concept">
              {decision
                ? conceptName(decision.concept_id)
                : question
                  ? conceptName(question.concept_id)
                  : "This practice session"}
            </p>
            {latest ? (
              <>
                <TeachingSource result={latest.result} />
                <p className="overview-next-copy">
                  {completed
                    ? "Your returned feedback and before/after evidence are ready to review."
                    : "Review what changed, read your explanation, then try the next question."}
                </p>
                {decision && (
                  <Disclosure title="Why this next?">
                    <p>{decision.reason}</p>
                  </Disclosure>
                )}
              </>
            ) : (
              <p className="overview-next-copy">
                Answer a short practice question. Your response helps update the
                concept estimate and choose what comes next.
              </p>
            )}
            <Button
              className="overview-cta rounded-xl bg-teal-dark text-white hover:bg-teal-dark/90 justify-between"
              onClick={onStudy}
              disabled={busy || !!error || !concepts.length}
            >
              {completed
                ? "Review this session"
                : latest
                  ? "Continue learning"
                  : "Start studying"}
              <ArrowRight size={17} aria-hidden="true" />
            </Button>
            <p className="overview-footnote">
              Practice uses the Intro AI question set. Presentation preferences
              change wording, not evidence.
            </p>
          </section>
        </div>
      </div>
      <aside className="overview-encouragement" aria-label="Practice reminder">
        <span className="overview-sprout">
          <Sprout size={25} strokeWidth={1.6} aria-hidden="true" />
        </span>
        <div>
          <h2>One question. A clearer next step.</h2>
          <p>
            {entries.length === 0
              ? "No answers submitted yet. Start wherever you are."
              : `${entries.length} ${entries.length === 1 ? "answer submitted" : "answers submitted"} in this session. Every returned estimate includes uncertainty.`}
          </p>
        </div>
      </aside>
    </section>
  );
}
