import { useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  Check,
  LoaderCircle,
  MessageSquare,
} from "lucide-react";
import type {
  ConceptEstimate,
  LearnerPresentationPreferences,
  PublicQuestion,
} from "../../../../contracts/api";
import { Button, Disclosure, Scene } from "../ui/primitives";
import { TeachingSource } from "./TeachingSource";
import { TeachingPreferences } from "./TeachingPreferences";
import { conceptName, percent, type StudyEntry } from "./model";

type Props = {
  entries: StudyEntry[];
  question: PublicQuestion | null;
  concepts: ConceptEstimate[];
  preferences: LearnerPresentationPreferences;
  onPreferencesChange: (value: LearnerPresentationPreferences) => void;
  busy: boolean;
  error: string;
  onManageMaterials?: () => void;
};

const prompts = [
  "Explain this differently",
  "Walk me through the example",
  "Help me compare these concepts",
];

export function StudyChatbot({
  entries,
  question,
  concepts,
  preferences,
  onPreferencesChange,
  busy,
  error,
  onManageMaterials,
}: Props) {
  const [draft, setDraft] = useState("");
  const composer = useRef<HTMLTextAreaElement>(null);
  const latestMessage = useRef<HTMLLIElement>(null);
  const latest = entries.at(-1);
  const currentConcept = question?.concept_id ?? latest?.question.concept_id;
  const estimate = concepts.find((c) => c.concept_id === currentConcept);

  function usePrompt(prompt: string) {
    setDraft(prompt);
    composer.current?.focus();
  }

  return (
    <section className="study-chatbot" aria-label="Chatbot workspace">
      <header className="chat-heading">
        <div className="chat-title">
          <MessageSquare size={20} aria-hidden="true" />
          <h2 id="chatbot-title" tabIndex={-1}>
            Study conversation
          </h2>
        </div>
        <span className="chat-mode">Demo</span>
      </header>
      <p className="chat-subtitle">
        Your answers and explanations, in one thread.
      </p>

      <div className="chat-layout">
        <div className="chat-main">
          <div
            className="chat-thread"
            role="region"
            aria-label="Study conversation"
            tabIndex={0}
          >
            {entries.length ? (
              <ol className="chat-messages">
                {entries.map((entry, index) => (
                  <li
                    key={`${entry.question.question_id}-${index}`}
                    ref={
                      index === entries.length - 1 ? latestMessage : undefined
                    }
                    tabIndex={-1}
                  >
                    <Scene>
                      <div className="chat-turn-label">
                        Question {index + 1}{" "}
                        <span>{conceptName(entry.question.concept_id)}</span>
                      </div>
                      <div className="chat-learner-message">
                        <span className="chat-speaker">
                          You · submitted answer
                        </span>
                        <p>
                          {entry.question.choices.find(
                            (choice) => choice.id === entry.answer,
                          )?.text ?? entry.answer}
                        </p>
                      </div>
                      <div className="chat-tutor-message">
                        <div className="chat-speaker">
                          <BookOpen size={14} aria-hidden="true" />
                          Study tutor <TeachingSource result={entry.result} />
                        </div>
                        <p
                          className={`chat-assessment chat-assessment-${entry.result.assessment.outcome}`}
                        >
                          {entry.result.assessment.feedback}
                        </p>
                        <div className="chat-response">
                          {entry.result.tutor.text
                            .split(/\n\s*\n/)
                            .map((paragraph, i) => (
                              <p key={i}>{paragraph}</p>
                            ))}
                        </div>
                      </div>
                    </Scene>
                  </li>
                ))}
              </ol>
            ) : (
              <div className="chat-empty">
                <span className="chat-empty-mark">
                  <MessageSquare
                    size={24}
                    strokeWidth={1.5}
                    aria-hidden="true"
                  />
                </span>
                <h3>A little space to work it out.</h3>
                <p>
                  Answer a practice question. Your feedback and the tutor’s
                  explanation will appear here.
                </p>
                <span>
                  <BookOpen size={14} aria-hidden="true" />
                  Connected to this study session
                </span>
              </div>
            )}
          </div>
          {entries.length > 0 && (
            <Button
              variant="ghost"
              className="chat-latest"
              onClick={() => {
                latestMessage.current?.scrollIntoView({
                  block: "nearest",
                  behavior: "instant",
                });
                latestMessage.current?.focus({ preventScroll: true });
              }}
            >
              <ArrowDown size={14} />
              Latest explanation
            </Button>
          )}
          <p className="chat-request-status" role="status">
            {error ? (
              "The practice request failed. Your previous explanations are still here."
            ) : busy ? (
              <>
                <LoaderCircle size={14} className="spin" />
                Waiting for the practice response…
              </>
            ) : latest ? (
              <>
                <Check size={14} />
                {entries.length}{" "}
                {entries.length === 1 ? "response" : "responses"} in this
                session
              </>
            ) : (
              "Explanations appear after you submit an answer."
            )}
          </p>

          <div className="chat-compose">
            <label htmlFor="chat-draft">Your follow-up draft</label>
            <div className="chat-prompts" aria-label="Suggested follow-ups">
              {prompts.map((prompt) => (
                <button
                  type="button"
                  key={prompt}
                  onClick={() => usePrompt(prompt)}
                >
                  {prompt}
                  <ArrowUp size={12} aria-hidden="true" />
                </button>
              ))}
            </div>
            <div className="chat-compose-field">
              <textarea
                ref={composer}
                id="chat-draft"
                rows={3}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                maxLength={2000}
                placeholder="What would you like to understand?"
                aria-describedby="chat-draft-note"
              />
              <div className="chat-compose-actions">
                <span>{draft.length}/2000</span>
                <Button disabled size="sm" aria-describedby="chat-draft-note">
                  <ArrowUp size={14} />
                  Send
                </Button>
              </div>
            </div>
            <p id="chat-draft-note">
              Draft only · follow-up messaging isn’t connected yet. Your draft
              stays here until you reset or leave this session.
            </p>
          </div>
        </div>
        <aside
          className="chat-tools"
          aria-label="Chatbot context and preferences"
        >
          <p className="chat-tools-label">IN THIS SESSION</p>
          <p className="chat-topic">
            {currentConcept
              ? conceptName(currentConcept)
              : "Waiting for a question"}
          </p>
          <Disclosure title="Context for this conversation">
            <dl className="chat-context">
              {question && (
                <div>
                  <dt>Current question</dt>
                  <dd>{question.prompt}</dd>
                </div>
              )}
              {latest && (
                <>
                  <div>
                    <dt>Latest feedback</dt>
                    <dd>{latest.result.assessment.feedback}</dd>
                  </div>
                  <div>
                    <dt>Selected activity</dt>
                    <dd>
                      {latest.result.decision
                        ? latest.result.decision.kind.replaceAll("_", " ")
                        : "Session complete"}
                    </dd>
                  </div>
                </>
              )}
              {estimate && (
                <div>
                  <dt>Concept evidence</dt>
                  <dd>
                    {estimate.evidence_count} observations ·{" "}
                    {percent(estimate.mean)} estimate
                    <br />
                    90% interval: {percent(estimate.interval90.lower)}–
                    {percent(estimate.interval90.upper)}
                  </dd>
                </div>
              )}
              <div>
                <dt>Conversation</dt>
                <dd>
                  {entries.length} submitted{" "}
                  {entries.length === 1 ? "answer" : "answers"}, with returned
                  explanations.
                </dd>
              </div>
            </dl>
            <p className="chat-context-note">
              This demo uses practice responses. Course files and setup goals
              have not been processed or sent to the tutor.
            </p>
          </Disclosure>
          {onManageMaterials && (
            <Button variant="ghost" onClick={onManageMaterials}>
              Manage materials
            </Button>
          )}
          <TeachingPreferences
            preferences={preferences}
            onChange={onPreferencesChange}
            busy={busy}
          />
        </aside>
      </div>
    </section>
  );
}
