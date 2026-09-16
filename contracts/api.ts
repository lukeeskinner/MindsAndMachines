// Minimal handwritten counterpart to models.py, owned with the shared contract.
export interface LearnerPresentationPreferences {
  plain_language: boolean;
  step_by_step: boolean;
  concise: boolean;
}
export interface PublicQuestion {
  question_id: string;
  concept_id: string;
  prompt: string;
  choices: { id: string; text: string }[];
}
export interface ConceptEstimate {
  concept_id: string;
  mean: number;
  interval90: { lower: number; upper: number };
  evidence_count: number;
}
export interface SessionResponse {
  session_id: string;
  question: PublicQuestion;
  concepts: ConceptEstimate[];
}
export interface TurnRequest {
  session_id: string;
  question_id: string;
  answer: string;
  presentation_preferences?: LearnerPresentationPreferences;
}
export interface TurnResponse {
  session_id: string;
  assessment: {
    outcome: 'correct' | 'incorrect' | 'unclear';
    misconception_id: string | null;
    feedback: string;
  };
  concepts: ConceptEstimate[];
  decision: {
    candidate_id: string;
    concept_id: string;
    kind: 'diagnostic_probe' | 'worked_example' | 'socratic_hint';
    reason: string;
  } | null;
  tutor: { text: string; fallback: boolean };
  next_question: PublicQuestion | null;
  mode: 'dummy';
  provider: 'fake';
  trace: string[];
}
