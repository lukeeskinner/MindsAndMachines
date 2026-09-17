import { useEffect, useRef, useState, type FormEvent } from "react";
import { MotionConfig, useReducedMotion } from "motion/react";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CalendarDays,
  Check,
  CheckCheck,
  Clock3,
  FileText,
  LockKeyhole,
} from "lucide-react";
import { BrandWordmark } from "../brand/Brand";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { NativeSelect, NativeSelectOption } from "../ui/native-select";
import { Scene } from "../ui/primitives";
import { Materials } from "./Materials";
import { CourseUpload } from "../course/CourseUpload";
import { useCourse } from "../course/CourseContext";
import {
  formatDate,
  goals,
  todayISO,
  validateDraft,
  type CourseDraft,
  type DraftErrors,
} from "./model";

const steps = [
  "Add your course",
  "Gather materials",
  "Set your goals",
  "You’re all set",
];
const sectionIds = ["course-section", "materials-section", "goals-section"];
export function Onboarding({
  draft,
  onChange,
  onContinue,
  onSignOut,
  signedInEmail,
}: {
  draft: CourseDraft;
  onChange: (draft: CourseDraft) => void;
  onContinue: () => void;
  onSignOut?: () => void;
  signedInEmail?: string;
}) {
  const course = useCourse();
  const selectedCourse = course?.selectedCourse;
  const uploaded = course && course.upload.status !== "idle";
  const processing = course?.upload.status === "processing";
  const readyCourse = course?.upload.status === "ready" ? course.upload.course : null;
  const startLabel = processing ? "Uploading course…"
    : readyCourse && readyCourse.course_id !== selectedCourse?.course_id ? "Start uploaded course"
    : selectedCourse ? "Continue selected course"
    : draft.files.length ? "Upload and start course" : "Open practice demo";
  async function startStudy() {
    if (processing) return;
    // A local file selection is intent to study those materials. Only enter
    // study after upload succeeds and the returned course is selected.
    const nextCourse = readyCourse ?? selectedCourse ?? (
      draft.files.length ? await course?.start(draft.files, draft.courseName) : null
    );
    if (nextCourse) {
      course?.selectCourse(nextCourse);
      onContinue();
    } else if (!draft.files.length) {
      onContinue();
    }
  }
  const [active, setActive] = useState(0);
  const [ready, setReady] = useState(false);
  const [errors, setErrors] = useState<DraftErrors>({});
  const form = useRef<HTMLFormElement>(null);
  const readyHeading = useRef<HTMLHeadingElement>(null);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (ready) readyHeading.current?.focus();
  }, [ready]);
  function update<K extends keyof CourseDraft>(key: K, value: CourseDraft[K]) {
    onChange({ ...draft, [key]: value });
    if (key in errors)
      setErrors((previous) => ({ ...previous, [key]: undefined }));
    if (key === "goal")
      setErrors((previous) => ({ ...previous, examDate: undefined }));
  }
  function goTo(index: number) {
    if (index === 3) {
      form.current?.requestSubmit();
      return;
    }
    setReady(false);
    setActive(index);
    requestAnimationFrame(() => {
      const section = document.getElementById(sectionIds[index]);
      section?.scrollIntoView({
        behavior: reduced ? "instant" : "smooth",
        block: "start",
      });
      section
        ?.querySelector<HTMLElement>('input:not([type="file"]),button,select')
        ?.focus({ preventScroll: true });
    });
  }
  function review(event: FormEvent) {
    event.preventDefault();
    const nextErrors = validateDraft(draft);
    setErrors(nextErrors);
    const first = Object.keys(nextErrors)[0];
    if (first) {
      setActive(first === "courseName" ? 0 : 2);
      requestAnimationFrame(() => document.getElementById(first)?.focus());
      return;
    }
    onChange({ ...draft, courseName: draft.courseName.trim() });
    setReady(true);
    setActive(3);
    window.scrollTo({ top: 0, behavior: reduced ? "instant" : "smooth" });
  }
  const complete = [
    !!draft.courseName.trim(),
    draft.files.length > 0 || ready,
    !Object.keys(validateDraft(draft)).length,
    ready,
  ];
  return (
    <MotionConfig reducedMotion="user">
      <div className="onboarding-shell">
        <a href="#course-setup" className="skip-link">
          Skip to course setup
        </a>
        <aside className="setup-rail">
          <a
            href="#/setup"
            className="setup-brand"
            aria-label="Minds and Machines course setup"
          >
            <BrandWordmark />
          </a>
          <div className="setup-rail-title">A SPACE TO MAKE IT CLICK</div>
          <nav aria-label="Course setup progress">
            <ol className="setup-steps">
              {steps.map((step, index) => (
                <li
                  key={step}
                  className={
                    index === active
                      ? "is-current"
                      : complete[index] && index < active
                        ? "is-complete"
                        : ""
                  }
                >
                  <button
                    type="button"
                    onClick={() => goTo(index)}
                    aria-current={index === active ? "step" : undefined}
                    aria-label={`${index + 1}. ${step}`}
                    disabled={ready && index === 3}
                  >
                    <span className="step-number" aria-hidden="true">
                      {complete[index] && index < active ? (
                        <Check size={15} />
                      ) : (
                        index + 1
                      )}
                    </span>
                    <span className="step-copy">
                      <span>{step}</span>
                      <small>
                        {index === 0
                          ? "Give your workspace a name"
                          : index === 1
                            ? "Bring what you have"
                            : index === 2
                              ? "Choose a focus and a pace"
                              : "Review, then begin"}
                      </small>
                    </span>
                  </button>
                </li>
              ))}
            </ol>
          </nav>
          <div className="setup-rail-bottom">
            <span className="rail-accent" />
            <p className="font-heading text-xl font-semibold leading-snug tracking-tight">
              A little context.
              <br />A clearer starting point.
            </p>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              You don’t need everything figured out. Start with a course and a
              goal.
            </p>
            <div className="local-draft-label">
              <LockKeyhole size={14} />
              <span>
                {signedInEmail ? `Signed in · ${signedInEmail}` : "Local draft"}
              </span>
            </div>
          </div>
        </aside>
        <main className="setup-main" id="course-setup" tabIndex={-1}>
          <header className="setup-topbar">
            <span className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="size-1.5 rounded-full bg-yellow" />
              {ready ? "SETUP REVIEW" : "COURSE SETUP"}
            </span>
            <div className="setup-topbar-actions">
              <Button
                variant="ghost"
                className="text-xs text-muted-foreground"
                onClick={() => void startStudy()}
                disabled={processing}
              >
                {startLabel}
                <ArrowRight size={14} />
              </Button>
              {onSignOut && (
                <Button
                  variant="ghost"
                  className="text-xs text-muted-foreground"
                  onClick={onSignOut}
                >
                  Sign out
                </Button>
              )}
            </div>
          </header>
          <div className="setup-content">
            {ready ? (
              <Scene key="ready">
                <div className="ready-symbol">
                  <CheckCheck size={29} strokeWidth={1.7} />
                </div>
                <p className="setup-eyebrow">A GOOD PLACE TO BEGIN</p>
                <h1 ref={readyHeading} tabIndex={-1} className="setup-heading">
                  Your course setup is ready.
                </h1>
                <p className="setup-intro">
                  Here’s the starting point you’ve put together.
                </p>
                <section
                  className="setup-summary"
                  aria-label="Course setup summary"
                >
                  <div className="summary-course">
                    <BookOpen size={23} />
                    <div>
                      <span className="text-xs text-muted-foreground">
                        YOUR COURSE
                      </span>
                      <h2 className="mt-1 break-words font-heading text-xl font-semibold">
                        {draft.courseName}
                      </h2>
                    </div>
                    <Button
                      variant="ghost"
                      className="ml-auto text-sm text-teal-dark"
                      onClick={() => goTo(0)}
                    >
                      Edit
                    </Button>
                  </div>
                  <dl className="summary-details">
                    <div>
                      <dt>Your focus</dt>
                      <dd>
                        {goals.find((goal) => goal.id === draft.goal)?.label}
                      </dd>
                    </div>
                    <div>
                      <dt>
                        {draft.goal === "exam" ? "Exam date" : "Target date"}
                      </dt>
                      <dd>{formatDate(draft.examDate)}</dd>
                    </div>
                    <div>
                      <dt>Time to study</dt>
                      <dd>
                        {draft.studyHours}{" "}
                        {draft.studyHours === "1" ? "hour" : "hours"} total
                      </dd>
                    </div>
                    <div>
                      <dt>Materials</dt>
                      <dd>
                        {draft.files.length
                          ? `${draft.files.length} ${draft.files.length === 1 ? "file" : "files"} selected`
                          : "Add them later"}
                      </dd>
                    </div>
                  </dl>
                  {draft.files.length > 0 && (
                    <ul
                      className="summary-files"
                      aria-label="Materials in your draft"
                    >
                      {draft.files.map((file, i) => (
                        <li key={`${file.name}-${i}`}>
                          <FileText size={15} />
                          <span className="truncate">{file.name}</span>
                          <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                            {uploaded ? "See upload status" : "Local only"}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
                <CourseUpload files={draft.files} title={draft.courseName} onActivated={onContinue} />
                <div className="setup-actions">
                  <Button variant="ghost" onClick={() => goTo(2)}>
                    <ArrowLeft size={16} />
                    Edit setup
                  </Button>
                  <Button onClick={() => void startStudy()} disabled={processing}>
                    {startLabel}
                    <ArrowRight size={17} />
                  </Button>
                </div>
              </Scene>
            ) : (
              <Scene key="form">
                <p className="setup-eyebrow">YOUR COURSE. YOUR PACE.</p>
                <h1 className="setup-heading">Let’s set up your course.</h1>
                <form ref={form} onSubmit={review} noValidate>
                  <section
                    id="course-section"
                    className="setup-section first-section"
                    onFocusCapture={() => setActive(0)}
                  >
                    <div className="setup-section-heading">
                      <span>01</span>
                      <h2>Your course</h2>
                    </div>
                    <label className="setup-label" htmlFor="courseName">
                      Course name
                    </label>
                    <Input
                      id="courseName"
                      name="courseName"
                      value={draft.courseName}
                      onChange={(event) =>
                        update("courseName", event.target.value)
                      }
                      placeholder="e.g. Cell biology"
                      maxLength={100}
                      autoComplete="off"
                      required
                      aria-invalid={!!errors.courseName}
                      aria-describedby={errors.courseName ? "course-error" : undefined}
                      className="bg-surface text-base"
                    />
                    {errors.courseName && (
                      <p
                        id="course-error"
                        className="setup-field-error"
                        role="alert"
                      >
                        {errors.courseName}
                      </p>
                    )}
                  </section>
                  <section
                    id="materials-section"
                    className="setup-section"
                    onFocusCapture={() => setActive(1)}
                    onDragEnter={() => setActive(1)}
                  >
                    <div className="setup-section-heading">
                      <span>02</span>
                      <h2>Course materials</h2>
                      <span className="optional-label">Optional</span>
                    </div>
                    <CourseUpload files={draft.files} title={draft.courseName} onActivated={onContinue} />
                    <Materials
                      files={draft.files}
                      onChange={(files) => update("files", files)}
                    />
                  </section>
                  <section
                    id="goals-section"
                    className="setup-section"
                    onFocusCapture={() => setActive(2)}
                  >
                    <div className="setup-section-heading">
                      <span>03</span>
                      <h2>Make it work for you</h2>
                    </div>
                    <fieldset>
                      <legend className="setup-label mb-3">
                        What are you working toward?
                      </legend>
                      <div className="goal-options">
                        {goals.map((goal) => (
                          <label
                            className={`goal-option ${draft.goal === goal.id ? "is-selected" : ""}`}
                            key={goal.id}
                          >
                            <input
                              type="radio"
                              name="learningGoal"
                              value={goal.id}
                              checked={draft.goal === goal.id}
                              onChange={() => update("goal", goal.id)}
                            />
                            <span className="goal-radio" aria-hidden="true">
                              {draft.goal === goal.id && <span />}
                            </span>
                            <span>
                              <strong>{goal.label}</strong>
                              <small>{goal.description}</small>
                            </span>
                          </label>
                        ))}
                      </div>
                    </fieldset>
                    <div className="goal-fields">
                      <div>
                        <label className="setup-label" htmlFor="examDate">
                          {draft.goal === "exam" ? "Exam date" : "Target date"}
                          {draft.goal !== "exam" && (
                            <span className="ml-1 font-normal text-muted-foreground">
                              (optional)
                            </span>
                          )}
                        </label>
                        <div className="relative">
                          <CalendarDays
                            size={17}
                            className="pointer-events-none absolute top-1/2 left-3.5 z-1 -translate-y-1/2 text-teal-dark"
                          />
                          <Input
                            id="examDate"
                            name="examDate"
                            type="date"
                            min={todayISO()}
                            value={draft.examDate}
                            required={draft.goal === "exam"}
                            onChange={(event) =>
                              update("examDate", event.target.value)
                            }
                            className="date-input bg-surface pl-10 text-base"
                            aria-invalid={!!errors.examDate}
                            aria-describedby={
                              errors.examDate ? "date-error" : undefined
                            }
                          />
                        </div>
                        {errors.examDate && (
                          <p
                            id="date-error"
                            className="setup-field-error"
                            role="alert"
                          >
                            {errors.examDate}
                          </p>
                        )}
                      </div>
                      <div>
                        <label className="setup-label" htmlFor="studyHours">
                          How much time can you study?
                        </label>
                        <NativeSelect
                          id="studyHours"
                          name="studyHours"
                          value={draft.studyHours}
                          onChange={(event) =>
                            update("studyHours", event.target.value)
                          }
                          aria-invalid={!!errors.studyHours}
                          aria-describedby="hours-help"
                          className="bg-surface text-base"
                        >
                          {["1", "3", "6", "10", "15"].map((hours) => (
                            <NativeSelectOption key={hours} value={hours}>
                              {hours} {hours === "1" ? "hour" : "hours"} total
                            </NativeSelectOption>
                          ))}
                        </NativeSelect>
                        <p id="hours-help" className="setup-field-hint">
                          Across your upcoming study sessions.
                        </p>
                      </div>
                    </div>
                  </section>
                  <div className="setup-form-footer">
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <Clock3 size={15} />
                      <span>You can revisit these choices.</span>
                    </div>
                    <Button
                      type="submit"
                      className="min-h-12 px-6 text-sm font-semibold"
                    >
                      Review my setup
                      <ArrowRight size={17} />
                    </Button>
                  </div>
                </form>
              </Scene>
            )}
          </div>
          <footer className="setup-footer">
            <span>MINDS & MACHINES</span>
          </footer>
        </main>
      </div>
    </MotionConfig>
  );
}
