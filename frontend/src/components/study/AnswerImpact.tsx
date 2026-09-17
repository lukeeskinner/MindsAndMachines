import { useCourseLabels } from "../course/CourseContext";
import { useId } from "react";
import { BetaDistributionPlot } from "./BetaDistributionPlot";
import {
  percent,
  intervalWidth,
  activityNames,
  type StudyEntry,
} from "./model";

export function AnswerModelDetails({ entry }: { entry: StudyEntry }) {
  const { conceptName } = useCourseLabels();
  const id = useId();
  const { question, result, before } = entry;
  const previous = before.find((c) => c.concept_id === question.concept_id);
  const current = result.concepts.find(
    (c) => c.concept_id === question.concept_id,
  );
  const comparable = previous && current;
  const unchanged = comparable && previous.mean === current.mean;
  return (
    <section className="answer-impact" aria-labelledby={`${id}-title`}>
      <h3 id={`${id}-title`}>Model comparison</h3>
      <p className="assessed-concept">
        Assessed concept · <strong>{conceptName(question.concept_id)}</strong>
      </p>
      <p className="impact-diagnosis">{result.assessment.feedback}</p>
      {comparable ? (
        <>
          <table className="snapshot-table">
            <caption className="sr-only">
              Before and after this answer for{" "}
              {conceptName(question.concept_id)}
            </caption>
            <thead>
              <tr>
                <th scope="col">Understanding</th>
                <th scope="col">Before</th>
                <th scope="col">After</th>
              </tr>
            </thead>
            <tbody>
              {previous.alpha != null && previous.beta != null && current.alpha != null && current.beta != null && (
                <tr>
                  <th scope="row">Beta parameters (α, β)</th>
                  <td>{previous.alpha}, {previous.beta}</td>
                  <td>{current.alpha}, {current.beta}</td>
                </tr>
              )}
              <tr>
                <th scope="row">Estimate</th>
                <td>{percent(previous.mean)}</td>
                <td>{percent(current.mean)}</td>
              </tr>
              <tr>
                <th scope="row">90% uncertainty range</th>
                <td>
                  {percent(previous.interval90.lower)} –{" "}
                  {percent(previous.interval90.upper)}
                </td>
                <td>
                  {percent(current.interval90.lower)} –{" "}
                  {percent(current.interval90.upper)}
                </td>
              </tr>
              <tr>
                <th scope="row">Interval width</th>
                <td>{intervalWidth(previous)} pp</td>
                <td>{intervalWidth(current)} pp</td>
              </tr>
              <tr>
                <th scope="row">Observations</th>
                <td>{previous.evidence_count}</td>
                <td>{current.evidence_count}</td>
              </tr>
            </tbody>
          </table>
          <p className="evidence-status">
            {current.evidence_count === previous.evidence_count
              ? "No new observation recorded."
              : current.evidence_count > previous.evidence_count
                ? "New observation recorded."
                : "The returned observation count decreased."}{" "}
            {unchanged
              ? "The understanding estimate is unchanged."
              : "The understanding estimate changed."}
          </p>
          {current.evidence_count === 0 && (
            <p className="impact-note">
              No evidence yet for this concept; this is a starting estimate.
            </p>
          )}
        </>
      ) : (
        <p className="evidence-status">
          A before/after comparison is unavailable for this concept.
        </p>
      )}
      <p className="impact-note">
        Experimental predicted success on comparable unaided questions. Interval
        width is measured in percentage points (pp). Explanations and
        presentation preferences do not add evidence.
      </p>
      <dl className="next-strategy">
        {result.decision && (
          <>
            <div>
              <dt>Next strategy</dt>
              <dd>
                {activityNames[result.decision.kind]}
                {result.decision.concept_id !== question.concept_id &&
                  ` · ${conceptName(result.decision.concept_id)}`}
              </dd>
            </div>
            <div>
              <dt>Why this next?</dt>
              <dd>{result.decision.reason}</dd>
            </div>
          </>
        )}
        <div>
          <dt>{result.next_question ? "Next question" : "Session complete"}</dt>
          <dd>
            {result.next_question ? (
              <>
                <span>{conceptName(result.next_question.concept_id)}</span>
                <p>{result.next_question.prompt}</p>
                <p className="impact-note">
                  {result.next_question.review
                    ? "Review item: seen before. This answer will not add mastery evidence."
                    : "After the explanation, answer this question to provide the next observation. Only accepted evidence updates the estimate."}
                </p>
              </>
            ) : (
              "No next question was returned. Review your session or start a new one."
            )}
          </dd>
        </div>
      </dl>
    </section>
  );
}

// Presentation of server snapshots only: no updates or policy scoring in the UI.
export function teachingPreview(text: string): string {
  // Keep complete, verbatim sentences (including decimals and math). The full
  // returned explanation remains in Chatbot; this is an excerpt, not a rewrite.
  return Array.from(new Intl.Segmenter("en", { granularity: "sentence" }).segment(text))
    .map(part => part.segment.trim()).filter(Boolean).slice(0, 3).join(" ");
}

export function AnswerImpact({ entry }: { entry: StudyEntry }) {
  const { conceptName } = useCourseLabels();
  const id = useId();
  const current = entry.result.concepts.find(c => c.concept_id === entry.question.concept_id);
  const previous = entry.before.find(c => c.concept_id === entry.question.concept_id);
  const reasons = entry.result.analytics?.focus_ranking.find(c => c.concept_id === entry.question.concept_id)?.reasons;
  return <section className="answer-impact" aria-labelledby={`${id}-title`}>
    <h3 id={`${id}-title`}>What changed?</h3>
    <p className="assessed-concept">{conceptName(entry.question.concept_id)}</p>
    {current ? <>
      <div className="impact-summary">
        <div className="impact-chart">
          <BetaDistributionPlot current={current} before={previous} beforeLabel="before this answer" simpleCaption />
        </div>
        <div className="impact-values">
          <p><strong>{percent(current.mean)}</strong> understanding estimate</p>
          {previous && previous.mean !== current.mean && <p className="estimate-change">{percent(previous.mean)} → {percent(current.mean)}</p>}
          <p>{current.evidence_count} {current.evidence_count === 1 ? "observation" : "observations"}</p>
          {reasons?.includes("high_uncertainty") && <p>Uncertainty is still high.</p>}
        </div>
      </div>
      {previous && current.evidence_count === previous.evidence_count && <p className="evidence-status">No new observation recorded.{previous.mean === current.mean && " The understanding estimate is unchanged."}</p>}
      {current.evidence_count === 0 && <p className="impact-note">No evidence yet for this concept; this is a starting estimate.</p>}
    </> : <p className="evidence-status">An estimate is unavailable for this concept.</p>}
  </section>;
}

export function NextStep({ entry }: { entry: StudyEntry }) {
  const { conceptName } = useCourseLabels();
  const next = entry.result.next_question;
  const reasons = entry.result.analytics?.focus_ranking.find(c => c.concept_id === next?.concept_id)?.reasons;
  return <div className="feedback-next">
    <h3>{next ? `Next: ${conceptName(next.concept_id).replace(/^\d+[.)]\s*/, "")}` : "Next: your session recap"}</h3>
    <p>{!next ? "Review your progress and choose what to practice next."
      : next.review ? "Review item: seen before. This answer will not add mastery evidence."
      : reasons?.some(r => r === "limited_evidence" || r === "high_uncertainty") ? "We still need more evidence on this concept."
      : "Try a fresh question to check your understanding."}</p>
  </div>;
}
