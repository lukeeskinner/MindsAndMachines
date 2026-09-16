import type { TurnResponse } from "../../../../contracts/api";

// These labels describe the returned Tutor output, not the whole turn.
// A fallback flag does not establish a provider failure or human review.
export function teachingLabel(result: TurnResponse): string {
  if (result.tutor.fallback) return "Marked fallback teaching";
  if (result.mode === "dummy" && result.provider === "fake")
    return "Deterministic teaching";
  return "Teaching source not reported";
}

export function TeachingSource({ result }: { result: TurnResponse }) {
  return (
    <span
      className={`tag teaching-source ${result.tutor.fallback ? "tag-fallback" : ""}`}
    >
      {teachingLabel(result)}
    </span>
  );
}
