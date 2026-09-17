import type { PublicCourse, SessionResponse } from "../../../contracts/api";
import { post } from "./api";

export type CourseFailure = "unsupported" | "invalid_files" | "too_large" | "processing" | "service" | "unavailable" | "missing";
export const courseMessages: Record<CourseFailure, string> = {
  unsupported: "Choose a PDF or PPTX file.",
  invalid_files: "Try fewer files, and check that each is a PDF or PPTX within the size limit.",
  too_large: "These materials are too large. Choose smaller files and try again.",
  processing: "We couldn’t process these materials. Try a different PDF or PPTX file.",
  service: "The course service is temporarily unavailable. Please try again later.",
  unavailable: "Course upload is unavailable. Your course has not been confirmed ready.",
  missing: "This course is no longer available. The service may have restarted. Upload the materials again or choose the demo.",
};
export class CourseError extends Error {
  constructor(public code: CourseFailure) { super(courseMessages[code]); }
}
export function courseErrorMessage(error: unknown) {
  return error instanceof CourseError ? error.message : courseMessages.service;
}
export type CourseUploadResult =
  | { status: "ready"; course: PublicCourse }
  | { status: "failed"; reason: CourseFailure };
export interface CourseUploadAdapter {
  upload(files: File[], title?: string): Promise<CourseUploadResult>;
}

// Explicit projection: never retain/display private extras from an upload response.
export function publicCourse(value: unknown): PublicCourse {
  const v = value as Partial<PublicCourse> | null;
  if (!v || typeof v.course_id !== "string" || !v.course_id ||
      typeof v.title !== "string" || !v.title.trim() ||
      !Array.isArray(v.concepts) || !v.concepts.length ||
      !v.concepts.every(c => c && typeof c.concept_id === "string" && c.concept_id && typeof c.display_name === "string" && c.display_name.trim()) ||
      new Set(v.concepts.map(c => c.concept_id)).size !== v.concepts.length ||
      !Array.isArray(v.source_filenames) || !v.source_filenames.every(s => typeof s === "string") ||
      !Number.isInteger(v.question_count) || v.question_count! < 1) throw new CourseError("processing");
  return {
    course_id: v.course_id, title: v.title,
    concepts: v.concepts.map(c => ({ concept_id: c.concept_id, display_name: c.display_name })),
    source_filenames: [...v.source_filenames], question_count: v.question_count!,
  };
}

// Processing completes within this multipart request. Only HTTP 201 confirms
// a ready PublicCourse; there is no status endpoint or background job contract.
export function createCourseUploadAdapter(path = "/api/v1/courses"): CourseUploadAdapter {
  return {
    async upload(files, title) {
      const body = new FormData();
      files.forEach(file => body.append("files", file));
      if (title?.trim()) body.append("title", title.trim());
      const response = await fetch(path, { method: "POST", body, signal: AbortSignal.timeout(120000) });
      if (!response.ok) {
        const code = response.status === 413 ? "too_large" : response.status === 415 ? "unsupported"
          : response.status === 400 ? "invalid_files"
          : response.status === 404 || response.status === 405 || response.status === 501 ? "unavailable"
          : response.status === 422 ? "processing" : "service";
        throw new CourseError(code);
      }
      if (response.status !== 201) throw new CourseError("service");
      return { status: "ready", course: publicCourse(await response.json()) };
    },
  };
}

export async function createSession(course?: PublicCourse | null): Promise<SessionResponse> {
  const result = await post<SessionResponse>("sessions", course ? { course_id: course.course_id } : {});
  // Older demo fixtures omit course_id. Uploaded sessions must echo it exactly.
  if ((result.course_id ?? null) !== (course?.course_id ?? null)) throw new CourseError("processing");
  if (course) {
    const ids = new Set(course.concepts.map(c => c.concept_id));
    if (!ids.has(result.question.concept_id) || result.concepts.length !== ids.size ||
        new Set(result.concepts.map(c => c.concept_id)).size !== ids.size ||
        result.concepts.some(c => !ids.has(c.concept_id))) throw new CourseError("processing");
  }
  return result;
}
