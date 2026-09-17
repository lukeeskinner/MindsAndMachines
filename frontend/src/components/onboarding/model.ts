export type LearningGoal = "exam" | "understand" | "review";
export type CourseDraft = {
  courseName: string;
  goal: LearningGoal;
  examDate: string;
  studyHours: string;
  files: File[];
};
export const initialDraft = (): CourseDraft => ({
  courseName: "Introduction to AI",
  goal: "exam",
  examDate: "",
  studyHours: "6",
  files: [],
});
export const goals: { id: LearningGoal; label: string; description: string }[] =
  [
    {
      id: "exam",
      label: "Prepare for an exam",
      description: "Work toward a date",
    },
    {
      id: "understand",
      label: "Build understanding",
      description: "Strengthen the foundations",
    },
    {
      id: "review",
      label: "Refresh a topic",
      description: "Pick up where you left off",
    },
  ];
export const MAX_FILES = 8;
export const MAX_FILE_BYTES = 20 * 1024 * 1024;
export const ACCEPTED_FILES = ".pdf,.pptx";
const extensions = new Set(ACCEPTED_FILES.split(",").map((s) => s.slice(1)));
export const fileKey = (file: File) =>
  `${file.name}:${file.size}:${file.lastModified}`;
export function selectFiles(current: File[], incoming: File[]) {
  const files = [...current];
  const errors: string[] = [];
  for (const file of incoming) {
    if (!extensions.has(file.name.split(".").at(-1)?.toLowerCase() ?? "")) {
      errors.push(`${file.name}: choose a PDF or PPTX file.`);
    } else if (file.size === 0) {
      errors.push(`${file.name}: this file is empty.`);
    } else if (file.size > MAX_FILE_BYTES) {
      errors.push(`${file.name}: the maximum file size is 20 MB.`);
    } else if (files.some((existing) => fileKey(existing) === fileKey(file))) {
      errors.push(`${file.name} is already selected.`);
    } else if (files.length >= MAX_FILES) {
      errors.push(
        `You can select up to ${MAX_FILES} files. Remove a file to add another.`,
      );
      break;
    } else files.push(file);
  }
  return { files, errors };
}
export const formatSize = (bytes: number) =>
  bytes >= 1024 * 1024
    ? `${(bytes / (1024 * 1024)).toFixed(1)} MB`
    : `${Math.max(1, Math.round(bytes / 1024))} KB`;
export function todayISO() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}
export type DraftErrors = Partial<
  Record<"courseName" | "examDate" | "studyHours", string>
>;
export function validateDraft(draft: CourseDraft): DraftErrors {
  const errors: DraftErrors = {};
  if (!draft.courseName.trim())
    errors.courseName = "Add a course name to continue.";
  if (draft.courseName.trim().length > 100)
    errors.courseName = "Keep the course name under 100 characters.";
  if (draft.goal === "exam" && !draft.examDate)
    errors.examDate = "Choose your exam date, or select a different goal.";
  if (
    draft.examDate &&
    (!/^\d{4}-\d{2}-\d{2}$/.test(draft.examDate) || draft.examDate < todayISO())
  )
    errors.examDate = "Choose today or a future date.";
  if (!["1", "3", "6", "10", "15"].includes(draft.studyHours))
    errors.studyHours = "Choose how much study time you have.";
  return errors;
}
export function formatDate(value: string) {
  if (!value) return "No date set";
  const [year, month, day] = value.split("-").map(Number);
  return new Intl.DateTimeFormat(undefined, {
    month: "long",
    day: "numeric",
    year: "numeric",
  }).format(new Date(year, month - 1, day));
}
