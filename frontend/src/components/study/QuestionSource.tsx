// Frontend presentation seam only. Populate solely from explicitly public
// question provenance once the upload/runtime workstream publishes that contract.
export type PublicQuestionSource = { filename: string; page?: number; slide?: number };
export function QuestionSource({ source }: { source?: PublicQuestionSource | null }) {
  if (!source?.filename) return null;
  const page = Number.isInteger(source.page) && source.page! > 0 ? source.page : undefined;
  const slide = Number.isInteger(source.slide) && source.slide! > 0 ? source.slide : undefined;
  return <p className="question-source" aria-label="Question source">
    Source: {source.filename}{page ? ` · page ${page}` : slide ? ` · slide ${slide}` : ""}
  </p>;
}
