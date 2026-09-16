import type { TurnResponse } from "../../../../contracts/api";

// These labels describe the returned Tutor output, not the whole turn.
// Explicit source establishes provenance; never infer it from prose or config.
export function teachingLabel(result: TurnResponse): string {
  if (result.tutor.teaching_source === "authored_fallback") return "Reviewed fallback";
  if (!result.tutor.fallback && result.tutor.teaching_source === "bedrock")
    return "AI-generated teaching";
  if (!result.tutor.fallback && result.tutor.teaching_source === "authored")
    return "Authored teaching";
  // Conservative labels for older responses without explicit provenance.
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
