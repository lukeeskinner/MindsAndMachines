import { createContext, useContext, useRef, useState, type ReactNode } from "react";
import type { PublicCourse } from "../../../../contracts/api";
import { courseErrorMessage, publicCourse, CourseError, createCourseUploadAdapter, type CourseUploadAdapter, type CourseUploadResult } from "../../lib/courses";
import { conceptNames } from "../study/model";

export type UploadState =
  | { status: "idle" }
  | { status: "processing" }
  | { status: "ready"; course: PublicCourse }
  | { status: "failed"; message: string };
const defaultAdapter = createCourseUploadAdapter();

function useController(adapter: CourseUploadAdapter = defaultAdapter) {
  const [selectedCourse, setSelectedCourse] = useState<PublicCourse | null>(null);
  const [upload, setUpload] = useState<UploadState>({ status: "idle" });
  const inFlight = useRef(false);
  function receive(result: CourseUploadResult) {
    if (result.status === "failed") throw new CourseError(result.reason);
    if (result.status === "ready") setUpload({ status: "ready", course: publicCourse(result.course) });
    else throw new CourseError("processing");
  }
  async function start(files: File[], title: string) {
    if (!files.length || inFlight.current) return;
    inFlight.current = true;
    setUpload({ status: "processing" });
    try { receive(await adapter.upload(files, title)); }
    catch (error) { setUpload({ status: "failed", message: courseErrorMessage(error) }); }
    finally { inFlight.current = false; }
  }
  return { selectedCourse, selectCourse: setSelectedCourse, upload, start,
    clearUpload: () => { if (!inFlight.current) setUpload({ status: "idle" }); },
  };
}
const CourseContext = createContext<ReturnType<typeof useController> | null>(null);
export function CourseProvider({ children, adapter }: { children: ReactNode; adapter?: CourseUploadAdapter }) {
  const controller = useController(adapter);
  return <CourseContext.Provider value={controller}>{children}</CourseContext.Provider>;
}
export function CourseBoundary({ children }: { children: ReactNode }) {
  const context = useContext(CourseContext);
  return context ? children : <CourseProvider>{children}</CourseProvider>;
}
export function useCourse() { return useContext(CourseContext); }
export function useCourseLabels() {
  const course = useCourse()?.selectedCourse;
  const names: Record<string, string> = course
    ? Object.fromEntries(course.concepts.map(c => [c.concept_id, c.display_name])) : conceptNames;
  return { course, title: course?.title ?? "Introduction to AI", names,
    conceptName: (id: string) => names[id] ?? id };
}
