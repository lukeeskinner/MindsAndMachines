import { useCourseLabels } from "../course/CourseContext";
import type { ConceptEstimate } from "../../../../contracts/api";
import { percent, intervalWidth } from "./model";

// Compare public snapshots for display; the server owns every estimate and count.
export function EvidenceComparison({
  before,
  after,
}: {
  before: ConceptEstimate[];
  after: ConceptEstimate[];
}) {
  const { conceptName } = useCourseLabels();
  const changes = after.flatMap((current) => {
    const previous = before.find(
      (item) => item.concept_id === current.concept_id,
    );
    if (
      !previous ||
      (previous.mean === current.mean &&
        previous.evidence_count === current.evidence_count &&
        previous.interval90.lower === current.interval90.lower &&
        previous.interval90.upper === current.interval90.upper)
    )
      return [];
    return [{ previous, current }];
  });
  return (
    <section
      className="evidence-comparison"
      aria-label="Returned concept changes"
    >
      <h3>What changed in this session</h3>
      {changes.length ? (
        <dl>
          {changes.map(({ previous, current }) => (
            <div key={current.concept_id}>
              <dt>{conceptName(current.concept_id)}</dt>
              <dd>
                Estimate: {percent(previous.mean)} →{" "}
                <strong>{percent(current.mean)}</strong>
              </dd>
              <dd>
                Observations: {previous.evidence_count} →{" "}
                <strong>{current.evidence_count}</strong>
              </dd>
              <dd>
                90% interval: {percent(previous.interval90.lower)}–
                {percent(previous.interval90.upper)} →{" "}
                {percent(current.interval90.lower)}–
                {percent(current.interval90.upper)}
              </dd>
              <dd>
                Interval width: {intervalWidth(previous)} →{" "}
                {intervalWidth(current)} percentage points
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p>The returned concept estimates and evidence counts are unchanged.</p>
      )}
    </section>
  );
}
