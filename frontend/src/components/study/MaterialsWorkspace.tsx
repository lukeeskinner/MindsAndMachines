import { useId, useRef, useState, type FormEvent } from "react";
import { Check, Pencil, FolderOpen } from "lucide-react";
import { Button, Scene } from "../ui/primitives";
import { Input } from "../ui/input";
import { NativeSelect } from "../ui/native-select";
import { Materials } from "../onboarding/Materials";
import { CourseUpload } from "../course/CourseUpload";
import { useCourseLabels } from "../course/CourseContext";
import {
  goals,
  formatDate,
  todayISO,
  validateDraft,
  type CourseDraft,
  type DraftErrors,
  type LearningGoal,
} from "../onboarding/model";

export function MaterialsWorkspace({
  draft,
  onChange,
}: {
  draft: CourseDraft;
  onChange: (draft: CourseDraft) => void;
}) {
  const { course } = useCourseLabels();
  const id = useId();
  const [editing, setEditing] = useState(false);
  const [values, setValues] = useState(draft);
  const [errors, setErrors] = useState<DraftErrors>({});
  const [saved, setSaved] = useState(false);
  const editButton = useRef<HTMLButtonElement>(null);
  const form = useRef<HTMLFormElement>(null);
  function close() {
    setEditing(false);
    requestAnimationFrame(() => editButton.current?.focus());
  }
  function save(event: FormEvent) {
    event.preventDefault();
    const nextErrors = validateDraft(values);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length) {
      requestAnimationFrame(() =>
        form.current
          ?.querySelector<HTMLElement>('[aria-invalid="true"]')
          ?.focus(),
      );
      return;
    }
    // Files may change while this editor is open. Keep the latest selected handles.
    onChange({
      ...values,
      courseName: values.courseName.trim(),
      files: draft.files,
    });
    setSaved(true);
    close();
  }
  return (
    <Scene>
      <section
        className="materials-workspace"
        aria-label="Course materials and goals"
      >
        <div className="materials-notice">
          <FolderOpen size={19} aria-hidden="true" />
          <p>
            <strong>{course ? course.title : "Your local course draft"}</strong>{" "}
            {course ? "This course is selected for study. Uploading other files does not change your session until you activate their course."
              : "Practice continues with the Intro AI demo until you activate a processed course."}
            {" "}Goals stay in this tab until refresh or sign-out.
          </p>
        </div>
        <div className="materials-columns">
          <section
            className="materials-library"
            aria-labelledby={`${id}-files`}
          >
            <header className="materials-section-heading">
              <div>
                <p className="eyebrow">01 / MATERIALS</p>
                <h2 id={`${id}-files`}>Your reading pile</h2>
              </div>
              <span className="tag">{draft.files.length} / 8 files</span>
            </header>
            <p className="materials-intro">
              {draft.files.length
                ? "Add or remove files as your course takes shape."
                : "Start with your lecture notes, or add them later."}
            </p>
            <CourseUpload files={draft.files} title={draft.courseName} />
            <Materials
              files={draft.files}
              inputLabel="Add materials to workspace"
              onChange={(files) => onChange({ ...draft, files })}
            />
          </section>
          <section className="materials-goals" aria-labelledby={`${id}-goals`}>
            <header className="materials-section-heading">
              <div>
                <p className="eyebrow">02 / YOUR DIRECTION</p>
                <h2 id={`${id}-goals`}>Course & goals</h2>
              </div>
            </header>
            {editing ? (
              <form
                ref={form}
                onSubmit={save}
                noValidate
                className="materials-editor"
              >
                <div>
                  <label htmlFor={`${id}-name`}>Course name</label>
                  <Input
                    autoFocus
                    id={`${id}-name`}
                    value={values.courseName}
                    maxLength={100}
                    aria-invalid={!!errors.courseName}
                    aria-describedby={
                      errors.courseName ? `${id}-name-error` : undefined
                    }
                    onChange={(e) =>
                      setValues({ ...values, courseName: e.target.value })
                    }
                  />
                  {errors.courseName && (
                    <p className="field-error" id={`${id}-name-error`}>
                      {errors.courseName}
                    </p>
                  )}
                </div>
                <div>
                  <label htmlFor={`${id}-goal`}>Study goal</label>
                  <NativeSelect
                    id={`${id}-goal`}
                    value={values.goal}
                    onChange={(e) =>
                      setValues({
                        ...values,
                        goal: e.target.value as LearningGoal,
                      })
                    }
                  >
                    {goals.map((goal) => (
                      <option key={goal.id} value={goal.id}>
                        {goal.label}
                      </option>
                    ))}
                  </NativeSelect>
                </div>
                <div>
                  <label htmlFor={`${id}-date`}>
                    {values.goal === "exam"
                      ? "Exam date"
                      : "Target date (optional)"}
                  </label>
                  <Input
                    id={`${id}-date`}
                    type="date"
                    min={todayISO()}
                    value={values.examDate}
                    aria-invalid={!!errors.examDate}
                    aria-describedby={
                      errors.examDate ? `${id}-date-error` : undefined
                    }
                    onChange={(e) =>
                      setValues({ ...values, examDate: e.target.value })
                    }
                  />
                  {errors.examDate && (
                    <p className="field-error" id={`${id}-date-error`}>
                      {errors.examDate}
                    </p>
                  )}
                </div>
                <div>
                  <label htmlFor={`${id}-hours`}>Study time available</label>
                  <NativeSelect
                    id={`${id}-hours`}
                    value={values.studyHours}
                    onChange={(e) =>
                      setValues({ ...values, studyHours: e.target.value })
                    }
                  >
                    {["1", "3", "6", "10", "15"].map((hours) => (
                      <option key={hours} value={hours}>
                        {hours} {hours === "1" ? "hour" : "hours"} total
                      </option>
                    ))}
                  </NativeSelect>
                </div>
                <p className="materials-local-note">
                  Save to keep changes in this tab. Leaving this view discards
                  unsaved edits.
                </p>
                <div className="materials-editor-actions">
                  <Button type="submit">
                    <Check size={15} />
                    Save changes
                  </Button>
                  <Button variant="ghost" onClick={close}>
                    Cancel
                  </Button>
                </div>
              </form>
            ) : (
              <>
                <dl className="materials-summary">
                  <div>
                    <dt>Course</dt>
                    <dd>{course?.title ?? (draft.courseName.trim() || "Not named yet")}</dd>
                  </div>
                  <div>
                    <dt>Goal</dt>
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
                    <dt>Time available</dt>
                    <dd>
                      {draft.studyHours}{" "}
                      {draft.studyHours === "1" ? "hour" : "hours"} total
                    </dd>
                  </div>
                </dl>
                <Button
                  ref={editButton}
                  variant="secondary"
                  onClick={() => {
                    setValues(draft);
                    setErrors({});
                    setSaved(false);
                    setEditing(true);
                  }}
                >
                  <Pencil size={14} />
                  Edit course goals
                </Button>
              </>
            )}
            <p className="materials-save-status" role="status">
              {saved && (
                <>
                  <Check size={14} />
                  Changes saved in this tab.
                </>
              )}
            </p>
          </section>
        </div>
      </section>
    </Scene>
  );
}
