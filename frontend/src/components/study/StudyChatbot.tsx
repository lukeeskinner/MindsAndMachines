import { useCourseLabels } from "../course/CourseContext";
import { Fragment, useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  BookOpen,
  Check,
  LoaderCircle,
  MessageSquare,
} from "lucide-react";
import type {
  CoachContext,
  ChatResponse,
  ConceptEstimate,
  LearnerPresentationPreferences,
  PublicQuestion,
} from "../../../../contracts/api";
import { Button, Disclosure, Scene } from "../ui/primitives";
import { TeachingSource } from "./TeachingSource";
import { TeachingPreferences } from "./TeachingPreferences";
import { percent, type StudyEntry } from "./model";

import { FocusRanking } from "./FocusRanking";
import { post, requestErrorMessage } from "../../lib/api";

type Props = {
  analytics?: CoachContext;
  onPractice?: (conceptId: string) => void;
  sessionId: string;
  onBusyChange: (value: boolean) => void;
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
  "How did I do and what should I focus on?",
  "Give me more practice on my weakest concept.",
  "Explain this differently",
  "Walk me through the example",
  "Help me compare these concepts",
];

export function StudyChatbot({
  analytics,
  onPractice,
  sessionId,
  onBusyChange,
  entries,
  question,
  concepts,
  preferences,
  onPreferencesChange,
  busy,
  error,
  onManageMaterials,
}: Props) {
  const { conceptName, course } = useCourseLabels();
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<(ChatResponse & { afterAnswerCount: number })[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [chatError, setChatError] = useState("");
  const sending = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const composer = useRef<HTMLTextAreaElement>(null);
  const chatThread = useRef<HTMLDivElement>(null);
  const latestChatMessage = useRef<HTMLLIElement>(null);
  const latestMessage = useRef<HTMLLIElement>(null);
  const latest = entries.at(-1);
  const currentConcept = question?.concept_id ?? latest?.question.concept_id;
  const estimate = concepts.find((c) => c.concept_id === currentConcept);

  async function send() {
    if (sending.current || busy || !sessionId || !draft.trim()) return;
    sending.current = true;
    setChatBusy(true); onBusyChange(true); setChatError("");
    const message = draft.trim();
    try {
      const result = await post<ChatResponse>("chat", {
        session_id: sessionId, message, presentation_preferences: preferences,
      });
      if (result.session_id !== sessionId || result.message !== message ||
          typeof result.text !== "string" || !result.text.trim() ||
          !["bedrock", "authored"].includes(result.teaching_source)) throw new Error("Invalid chat response");
      if (!mounted.current) return;
      setMessages(previous => [...previous, { ...result, afterAnswerCount: entries.length }]); setDraft("");
    } catch (err) {
      if (mounted.current) setChatError(requestErrorMessage(err));
    } finally {
      sending.current = false;
      if (mounted.current) { setChatBusy(false); onBusyChange(false); }
    }
  }

  useEffect(() => {
    // Scroll only the conversation region, never steal focus or jump another view.
    if (chatThread.current && messages.length) chatThread.current.scrollTop = chatThread.current.scrollHeight;
  }, [messages.length]);

  function renderMessage(message: ChatResponse, index: number) {
    return <li key={`chat-${index}`} ref={message === messages.at(-1) ? latestChatMessage : undefined} tabIndex={-1}>
      <Scene>
        <div className="chat-learner-message"><span className="chat-speaker">You</span><p>{message.message}</p></div>
        <div className="chat-tutor-message">
          <span className="chat-speaker">Study tutor · {message.teaching_source === "bedrock" ? "AI-generated response" : "Local study notes"}</span>
          {message === messages.at(-1) && message.practice_concept_id && onPractice && <Button disabled={busy} onClick={() => onPractice(message.practice_concept_id!)}>Practice this concept</Button>}
          <div className="chat-response">{message.text.split(/\n\s*\n/).map((paragraph, i) => <p key={i}>{paragraph}</p>)}</div>
        </div>
      </Scene>
    </li>;
  }

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
        <span className="chat-mode">Session tutor</span>
      </header>
      <p className="chat-subtitle">
        Ask about your course, or revisit your practice explanations.
      </p>

      <div className="chat-layout">
        <div className="chat-main">
          <div
            ref={chatThread}
            className="chat-thread"
            role="region"
            aria-label="Study conversation"
            tabIndex={0}
          >
            {entries.length || messages.length ? (
              <ol className="chat-messages">
                {messages.filter(message => message.afterAnswerCount === 0).map(renderMessage)}
                {entries.map((entry, index) => (
                  <Fragment key={`${entry.question.question_id}-${index}`}><li
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
                  {messages.filter(message => message.afterAnswerCount === index + 1).map(renderMessage)}
                  </Fragment>
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
                  Ask a question about this course. Your messages and practice explanations stay in this session.
                </p>
                <span>
                  <BookOpen size={14} aria-hidden="true" />
                  Connected to this study session
                </span>
              </div>
            )}
          </div>
          {(entries.length > 0 || messages.length > 0) && (
            <Button
              variant="ghost"
              className="chat-latest"
              onClick={() => {
                const target = messages.at(-1)?.afterAnswerCount === entries.length ? latestChatMessage.current : latestMessage.current;
                target?.scrollIntoView({
                  block: "nearest",
                  behavior: "instant",
                });
                target?.focus({ preventScroll: true });
              }}
            >
              <ArrowDown size={14} />
              Latest response
            </Button>
          )}
          <p className="chat-request-status" role="status">
            {chatError ? (
              "Your message wasn’t sent. Your draft is preserved; please retry."
            ) : chatBusy ? (
              <><LoaderCircle size={14} className="spin" />Thinking about your question…</>
            ) : error ? (
              "The practice request failed. Your previous explanations are still here."
            ) : busy ? (
              <>
                <LoaderCircle size={14} className="spin" />
                Waiting for the practice response…
              </>
            ) : latest || messages.length ? (
              <>
                <Check size={14} />
                {entries.length + messages.length}{" "}
                {entries.length + messages.length === 1 ? "response" : "responses"} in this
                session
              </>
            ) : (
              "Ask a question whenever you need a different explanation."
            )}
          </p>

          {chatError && <p role="alert">{chatError}</p>}
          <div className="chat-compose">
            <label htmlFor="chat-draft">Your message</label>
            <div className="chat-prompts" aria-label="Suggested follow-ups">
              {prompts.map((prompt) => (
                <button
                  type="button"
                  key={prompt}
                  disabled={busy}
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
                disabled={chatBusy}
                maxLength={2000}
                placeholder="What would you like to understand?"
                aria-describedby="chat-draft-note"
              />
              <div className="chat-compose-actions">
                <span>{draft.length}/2000</span>
                <Button disabled={busy || !sessionId || !draft.trim()} onClick={() => void send()} size="sm" aria-describedby="chat-draft-note">
                  <ArrowUp size={14} />
                  Send
                </Button>
              </div>
            </div>
            <p id="chat-draft-note">
              Course-grounded conversation. Chat does not grade answers or change your mastery. Reset starts a fresh conversation.
            </p>
          </div>
        </div>
        <aside
          className="chat-tools"
          aria-label="Chatbot context and preferences"
        >
          <FocusRanking analytics={analytics} busy={busy} onPractice={onPractice} />
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
                  explanations; {messages.length} chat replies.
                </dd>
              </div>
            </dl>
            <p className="chat-context-note">
              {course ? `This session uses ${course.title}. Sources: ${course.source_filenames.join(", ")}. Setup goals remain local.`
                : "This demo uses practice responses. Local setup files and goals are not used in this demo session."}
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
