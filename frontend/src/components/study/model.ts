import type {
  ConceptEstimate,
  PublicQuestion,
  TurnResponse,
} from "../../../../contracts/api";

export type StudyEntry = {
  question: PublicQuestion;
  answer: string;
  result: TurnResponse;
  before: ConceptEstimate[];
};

export const conceptNames: Record<string, string> = {
  bfs: "Breadth-first search",
  ucs: "Uniform-cost search",
  astar: "A* search",
  admissibility: "Admissibility",
  consistency: "Consistency",
  admissibility_vs_consistency: "Admissibility vs consistency",
};

export const conceptName = (id: string) => conceptNames[id] ?? id;
export const activityNames = {
  worked_example: "Worked example",
  diagnostic_probe: "Diagnostic probe",
  socratic_hint: "Socratic hint",
};
export const intervalWidth = (concept: ConceptEstimate) =>
  ((concept.interval90.upper - concept.interval90.lower) * 100).toFixed(1);

export const percent = (value: number) => `${(value * 100).toFixed(1)}%`;
