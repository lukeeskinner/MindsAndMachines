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
export interface PublicCourseConcept {
  concept_id: string;
  display_name: string;
}
export interface PublicCourse {
  course_id: string;
  title: string;
  concepts: PublicCourseConcept[];
  source_filenames: string[];
  question_count: number;
}
export interface SessionRequest {
  course_id?: string | null;
}
export interface SessionResponse {
  session_id: string;
  course_id: string | null;
  question: PublicQuestion;
  concepts: ConceptEstimate[];
  question_count: number;
  flashcards: Flashcard[];
}
export interface Flashcard {
  card_id: string;
  concept_id: string;
  front: string;
  back: string;
  source: string;
}
export interface TurnRequest {
  session_id: string;
  question_id: string;
  answer: string;
  presentation_preferences?: LearnerPresentationPreferences;
}
export interface TurnResponse {
  flashcards?: Flashcard[];
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
  tutor: {
    text: string;
    fallback: boolean;
    teaching_source: 'authored' | 'bedrock' | 'authored_fallback';
  };
  next_question: PublicQuestion | null;
  mode: 'dummy' | 'live';
  provider: 'fake' | 'bedrock';
  trace: string[];
}
