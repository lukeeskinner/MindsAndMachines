import { useId } from "react";
import { Button } from "../ui/button";
import { useCourse } from "./CourseContext";

export function CourseUpload({ files, title, onActivated }: { files: File[]; title: string; onActivated?: () => void }) {
  const controller = useCourse();
  const id = useId();
  if (!controller) return null;
  const { upload, selectedCourse, selectCourse, start } = controller;
  const pending = upload.status === "processing";
  return <section className="course-upload" aria-label="Course upload" data-state={upload.status === "idle" && files.length ? "selected" : upload.status}>
    <p id={id} role="status">
      {upload.status === "idle" && (files.length ? "Materials selected. They have not been uploaded or processed." : "Select PDF or PPTX materials to prepare a course.")}
      {upload.status === "processing" && "Uploading and processing your materials. Waiting for your course to be ready."}
      {upload.status === "ready" && "Course ready. Activate it to start a new course session."}
    </p>
    {upload.status === "failed" && <p role="alert">{upload.message}</p>}
    {upload.status === "ready" ? <>
      <h3>{upload.course.title}</h3>
      <p>{upload.course.question_count} questions · {upload.course.concepts.length} concepts</p>
      <ul aria-label="Processed course concepts">{upload.course.concepts.map(c => <li key={c.concept_id}>{c.display_name}</li>)}</ul>
      <p>Source files: {upload.course.source_filenames.join(", ") || "Not reported"}</p>
      <Button type="button" disabled={selectedCourse?.course_id === upload.course.course_id} onClick={() => {
        selectCourse(upload.course); onActivated?.();
      }}>{selectedCourse?.course_id === upload.course.course_id ? "Course selected" : "Activate course"}</Button>
    </> : <Button type="button" aria-describedby={id} aria-busy={pending} disabled={!files.length || pending} onClick={() => void start(files, title)}>
      {upload.status === "failed" ? "Retry upload" : "Upload course"}
    </Button>}
    {upload.status === "ready" && <Button type="button" variant="ghost" onClick={controller.clearUpload}>Prepare another course</Button>}
    {selectedCourse && <Button type="button" variant="ghost" onClick={() => { selectCourse(null); onActivated?.(); }}>Use demo course</Button>}
  </section>;
}
