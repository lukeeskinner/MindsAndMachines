// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { PublicCourse, SessionResponse } from "../../contracts/api";
import fixture from "../../contracts/fixtures/turn_response.json";
import { App } from "../src/App";
import { RootApp } from "../src/RootApp";
import { CourseProvider } from "../src/components/course/CourseContext";
import { QuestionSource } from "../src/components/study/QuestionSource";
import { CourseError, createCourseUploadAdapter, createSession, publicCourse, type CourseUploadAdapter } from "../src/lib/courses";
import { MAX_FILE_BYTES, selectFiles } from "../src/components/onboarding/model";

const biology: PublicCourse = {
  course_id: "biology", title: "Cell biology",
  // Deliberate ID collision: uploaded display names must still win over demo names.
  concepts: [{ concept_id: "admissibility", display_name: "Cell membranes" }, { concept_id: "osmosis", display_name: "Osmosis" }],
  source_filenames: ["cells.pdf", "transport.pptx"], question_count: 7,
};
const chemistry: PublicCourse = { course_id: "chemistry", title: "Chemical bonds", concepts: [{ concept_id: "bonds", display_name: "Covalent bonds" }], source_filenames: ["bonds.pdf"], question_count: 3 };
const demo: SessionResponse = { session_id: "demo-session", course_id: null, question: fixture.next_question, concepts: fixture.concepts };
function session(course: PublicCourse): SessionResponse {
  return { session_id: `${course.course_id}-session`, course_id: course.course_id,
    question: { question_id: `${course.course_id}-q1`, concept_id: course.concepts[0].concept_id, prompt: `A question about ${course.title}`, choices: [{ id: "a", text: `Answer for ${course.title}` }, { id: "unsure", text: "I'm not sure yet." }] },
    concepts: course.concepts.map(c => ({ concept_id: c.concept_id, mean: 0.5, interval90: { lower: 0.05, upper: 0.95 }, evidence_count: 0 })),
  };
}
const response = (body: unknown, status = 200) => ({ ok: status < 400, status, json: async () => body });
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; }
let fetchMock = vi.fn();
beforeEach(() => {
  window.sessionStorage.clear();
  window.history.replaceState(null, "", "/");
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  Element.prototype.scrollIntoView = vi.fn();
  fetchMock = vi.fn().mockImplementation(async (_path, options) => {
    const body = JSON.parse(options.body);
    return response(body.course_id === biology.course_id ? session(biology) : body.course_id === chemistry.course_id ? session(chemistry) : demo);
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
const pdf = () => new File(["public lecture"], "cells.pdf", { type: "application/pdf" });
function readyAdapter(course = biology): CourseUploadAdapter { return { upload: vi.fn().mockResolvedValue({ status: "ready", course }) }; }
async function materials(adapter?: CourseUploadAdapter) {
  const user = userEvent.setup({ applyAccept: false });
  render(<CourseProvider adapter={adapter}><App /></CourseProvider>);
  await screen.findByRole("radio", { name: demo.question.choices[0].text });
  await user.click(screen.getByRole("tab", { name: "Materials" }));
  return user;
}
async function uploadAndActivate(user: ReturnType<typeof userEvent.setup>) {
  await user.upload(screen.getByLabelText("Add materials to workspace"), pdf());
  await user.click(screen.getByRole("button", { name: "Upload course" }));
  await user.click(await screen.findByRole("button", { name: "Activate course" }));
  await screen.findByRole("radio", { name: "Answer for Cell biology" });
}

describe("truthful course upload", () => {
  it("supports PDF/PPTX, rejects other files and oversized materials, and waits for an explicit upload", async () => {
    const user = await materials();
    const input = screen.getByLabelText("Add materials to workspace");
    expect(input.getAttribute("accept")).toBe(".pdf,.pptx");
    await user.upload(input, [pdf(), new File(["slides"], "slides.PPTX"), new File(["text"], "notes.txt"), new File(["doc"], "notes.docx")]);
    expect(screen.getByRole("list", { name: "Selected course materials" }).textContent).toContain("slides.PPTX");
    expect(screen.getByRole("alert").textContent).toContain("choose a PDF or PPTX");
    const upload = screen.getByRole("button", { name: "Upload course" }) as HTMLButtonElement;
    expect(upload.disabled).toBe(false);
    expect(screen.queryByText(/Course upload isn’t connected yet/)).toBeNull();
    expect(screen.getByRole("region", { name: "Course upload" }).getAttribute("data-state")).toBe("selected");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const big = pdf(); Object.defineProperty(big, "size", { value: MAX_FILE_BYTES + 1 });
    expect(selectFiles([], [big]).errors[0]).toContain("maximum file size");
  });

  it("posts with the production adapter, announces pending processing, and uses confirmed metadata without polling", async () => {
    const sending = deferred<ReturnType<typeof response>>();
    const user = await materials();
    fetchMock.mockReturnValueOnce(sending.promise);
    await user.upload(screen.getByLabelText("Add materials to workspace"), pdf());
    const upload = screen.getByRole("button", { name: "Upload course" });
    upload.focus(); await user.keyboard("{Enter}");
    const region = screen.getByRole("region", { name: "Course upload" });
    expect(region.getAttribute("data-state")).toBe("processing");
    expect(within(region).getByRole("status").textContent).toContain("Uploading and processing");
    expect(upload.getAttribute("aria-busy")).toBe("true");
    expect((upload as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("button", { name: "Activate course" })).toBeNull();
    expect((screen.getByRole("button", { name: "Remove cells.pdf" }) as HTMLButtonElement).disabled).toBe(true);
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual(["/api/v1/sessions", "/api/v1/courses"]);
    expect(fetchMock.mock.calls[1][1].body).toBeInstanceOf(FormData);
    expect(fetchMock.mock.calls[1][1].method).toBe("POST");
    await act(async () => sending.resolve(response({ ...biology, answer_key: "SECRET KEY", rubric: "SECRET RUBRIC", source_quotes: ["PRIVATE QUOTE"] }, 201)));
    await screen.findByRole("button", { name: "Activate course" });
    expect(region.getAttribute("data-state")).toBe("ready");
    expect(region.textContent).toContain("7 questions · 2 concepts");
    expect(region.textContent).toContain("Cell membranes");
    expect(region.textContent).toContain("transport.pptx");
    expect(region.textContent).not.toMatch(/SECRET|PRIVATE/);
    expect(fetchMock).toHaveBeenCalledTimes(2); // Ready does not automatically activate.
    await user.click(screen.getByRole("button", { name: "Activate course" }));
    await screen.findByRole("radio", { name: "Answer for Cell biology" });
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ course_id: "biology" });
    await user.click(screen.getByRole("button", { name: "New practice session" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(4));
    expect(JSON.parse(fetchMock.mock.calls[3][1].body)).toEqual({ course_id: "biology", previous_session_id: "biology-session", reset_learner: false });
    await user.click(screen.getByRole("tab", { name: "Materials" }));
    await user.click(screen.getByRole("button", { name: "Use demo course" }));
    await screen.findByRole("radio", { name: demo.question.choices[0].text });
    expect(JSON.parse(fetchMock.mock.calls[4][1].body)).toEqual({});
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual([
      "/api/v1/sessions", "/api/v1/courses", "/api/v1/sessions", "/api/v1/sessions", "/api/v1/sessions",
    ]);
    expect(fetchMock.mock.calls.every(call => call[1].method === "POST")).toBe(true);
  });

  it.each([
    [415, "Choose a PDF or PPTX"],
    [400, "Try fewer files"],
    [413, "too large"],
    [422, "couldn’t build a valid study course"],
    [500, "temporarily unavailable"],
    [502, "temporarily unavailable"],
    [503, "temporarily unavailable"],
    [404, "Course upload is unavailable"],
  ])("renders controlled HTTP %s upload failures safely", async (status, message) => {
    const user = await materials();
    fetchMock.mockResolvedValueOnce(response({ detail: "SECRET provider stack, private source quotes and rubric" }, status as number));
    await user.upload(screen.getByLabelText("Add materials to workspace"), pdf());
    await user.click(screen.getByRole("button", { name: "Upload course" }));
    expect((await screen.findByRole("alert")).textContent).toContain(message);
    expect(document.body.textContent).not.toMatch(/SECRET|provider stack|private source quotes/);
    expect(screen.queryByRole("button", { name: "Activate course" })).toBeNull();
    expect((screen.getByRole("button", { name: "Retry upload" }) as HTMLButtonElement).disabled).toBe(false);
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual(["/api/v1/sessions", "/api/v1/courses"]);
  });

  it("handles network failure safely and retries the same upload endpoint", async () => {
    const user = await materials();
    fetchMock.mockRejectedValueOnce(new TypeError("SECRET network exception"));
    await user.upload(screen.getByLabelText("Add materials to workspace"), pdf());
    await user.click(screen.getByRole("button", { name: "Upload course" }));
    expect((await screen.findByRole("alert")).textContent).toContain("temporarily unavailable");
    expect(document.body.textContent).not.toContain("SECRET");
    fetchMock.mockResolvedValueOnce(response(biology, 201));
    await user.click(screen.getByRole("button", { name: "Retry upload" }));
    await screen.findByRole("button", { name: "Activate course" });
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual(["/api/v1/sessions", "/api/v1/courses", "/api/v1/courses"]);
  });

  it.each(["unsupported", "too_large", "processing", "service"] as const)("reports %s failures with a retry and no server exceptions", async code => {
    const adapter = { upload: vi.fn().mockResolvedValueOnce({ status: "failed", reason: code }).mockRejectedValueOnce(new Error("private provider stack")) };
    const user = await materials(adapter);
    await user.upload(screen.getByLabelText("Add materials to workspace"), pdf());
    await user.click(screen.getByRole("button", { name: "Upload course" }));
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Activate course" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Retry upload" }));
    expect(screen.getByRole("alert").textContent).toContain("temporarily unavailable");
    expect(document.body.textContent).not.toContain("private provider stack");
  });

  it("preserves upload state between onboarding and workspace and activates from onboarding", async () => {
    window.sessionStorage.setItem("minds-machines-auth", JSON.stringify({ email: "test@example.com", signedInAt: "2026-09-16" }));
    const user = userEvent.setup();
    fetchMock.mockResolvedValueOnce(response(biology, 201));
    render(<RootApp />);
    await user.upload(screen.getByLabelText("Choose course materials"), pdf());
    await user.click(screen.getByRole("button", { name: "Upload course" }));
    await user.click(await screen.findByRole("button", { name: "Activate course" }));
    await screen.findByRole("radio", { name: "Answer for Cell biology" });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/courses");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ course_id: "biology" });
    await user.click(screen.getByRole("tab", { name: "Materials" }));
    expect(screen.getByRole("button", { name: "Course selected" })).toBeTruthy();
    expect(screen.getByRole("list", { name: "Processed course concepts" }).textContent).toContain("Osmosis");
  });
});

describe("course activation and isolation", () => {
  it("activates an already uploaded course through the main start button and replaces an existing demo session", async () => {
    window.sessionStorage.setItem("minds-machines-auth", JSON.stringify({ email: "test@example.com", signedInAt: "2026-09-16" }));
    const user = userEvent.setup();
    render(<RootApp />);
    await user.click(screen.getByRole("button", { name: "Open practice demo" }));
    await screen.findByRole("radio", { name: demo.question.choices[0].text });
    await user.click(screen.getByRole("button", { name: "Course setup" }));
    await user.upload(screen.getByLabelText("Choose course materials"), pdf());
    fetchMock.mockResolvedValueOnce(response(biology, 201));
    await user.click(screen.getByRole("button", { name: "Upload course" }));
    await user.click(await screen.findByRole("button", { name: "Start uploaded course" }));
    await screen.findByRole("radio", { name: "Answer for Cell biology" });
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual(["/api/v1/sessions", "/api/v1/courses", "/api/v1/sessions"]);
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ course_id: biology.course_id });
    expect(document.body.textContent).not.toMatch(/Introduction to AI|Search & heuristics/);
    expect(screen.queryByRole("radio", { name: demo.question.choices[0].text })).toBeNull();
  });

  it("stays in setup after upload failure and retries without creating a demo session", async () => {
    window.sessionStorage.setItem("minds-machines-auth", JSON.stringify({ email: "test@example.com", signedInAt: "2026-09-16" }));
    const user = userEvent.setup();
    render(<RootApp />);
    await user.upload(screen.getByLabelText("Choose course materials"), pdf());
    fetchMock.mockResolvedValueOnce(response({ detail: "private failure" }, 503));
    await user.click(screen.getByRole("button", { name: "Upload and start course" }));
    await screen.findByRole("alert");
    expect(screen.queryByRole("tab", { name: "Study desk" })).toBeNull();
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual(["/api/v1/courses"]);
    fetchMock.mockResolvedValueOnce(response(biology, 201));
    await user.click(screen.getByRole("button", { name: "Upload and start course" }));
    await screen.findByRole("radio", { name: "Answer for Cell biology" });
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual(["/api/v1/courses", "/api/v1/courses", "/api/v1/sessions"]);
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ course_id: biology.course_id });
  });

  it.each([false, true])("starts selected Grad Algorithms materials from onboarding (review=%s), never a demo session", async review => {
    const algorithms: PublicCourse = {
      course_id: "course_grad_algorithms", title: "Grad Algorithms",
      concepts: [{ concept_id: "dynamic_programming", display_name: "Dynamic programming" }],
      source_filenames: ["grad-algorithms.pptx"], question_count: 2,
    };
    window.sessionStorage.setItem("minds-machines-auth", JSON.stringify({ email: "test@example.com", signedInAt: "2026-09-16" }));
    const uploaded = deferred<ReturnType<typeof response>>();
    fetchMock.mockImplementation(async (path, options) => {
      if (path === "/api/v1/courses") return uploaded.promise;
      return response(JSON.parse(options.body).course_id === algorithms.course_id ? session(algorithms) : demo);
    });
    const user = userEvent.setup();
    render(<RootApp />);
    await user.clear(screen.getByRole("textbox", { name: "Course name" }));
    await user.type(screen.getByRole("textbox", { name: "Course name" }), algorithms.title);
    await user.upload(screen.getByLabelText("Choose course materials"), new File(["lecture"], "grad-algorithms.pptx"));
    if (review) {
      await user.click(screen.getByRole("radio", { name: /Build understanding/ }));
      await user.click(screen.getByRole("button", { name: "Review my setup" }));
    }
    const start = screen.getAllByRole("button", { name: /^(Open practice demo|Upload and start course)$/ }).at(-1)!;
    await user.click(start);
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual(["/api/v1/courses"]);
    expect(fetchMock.mock.calls[0][1].body.get("title")).toBe("Grad Algorithms");
    expect((start as HTMLButtonElement).disabled).toBe(true);
    expect(screen.queryByRole("tabpanel", { name: "Study desk" })).toBeNull();
    await act(async () => uploaded.resolve(response(algorithms, 201)));
    await screen.findByRole("radio", { name: "Answer for Grad Algorithms" });
    expect(fetchMock.mock.calls.map(call => call[0])).toEqual(["/api/v1/courses", "/api/v1/sessions"]);
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ course_id: algorithms.course_id });
    expect(document.body.textContent).toContain("Dynamic programming");
    expect(document.body.textContent).not.toMatch(/Introduction to AI|Search & heuristics|Admissibility|admissible|consistent heuristic/);
    await user.click(screen.getByRole("button", { name: "New practice session" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(JSON.parse(fetchMock.mock.calls[2][1].body)).toEqual({ course_id: algorithms.course_id, previous_session_id: algorithms.course_id + "-session", reset_learner: false });
  });

  it("sends course_id, renders dynamic labels everywhere, and resets within the course while preserving preferences", async () => {
    const user = await materials(readyAdapter());
    await uploadAndActivate(user);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({});
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ course_id: "biology" });
    await user.click(screen.getByRole("switch", { name: /Keep it concise/ }));
    for (const tab of ["Home", "Concept map", "Chatbot", "Materials", "Study desk"]) {
      await user.click(screen.getByRole("tab", { name: tab, exact: true }));
      const panel = screen.getByRole("tabpanel", { name: tab });
      expect(panel.textContent).not.toMatch(/Intro AI|Introduction to AI|Search & heuristics|Heuristic properties|Admissibility|Breadth-first/);
    }
    await user.click(screen.getByRole("tab", { name: "Concept map" }));
    const selected = screen.getByRole("region", { name: "Selected concept evidence" });
    expect(selected.textContent).toContain("Cell membranes");
    expect(selected.textContent).toContain("50.0%");
    await user.click(screen.getByRole("button", { name: "New practice session" }));
    await screen.findByRole("radio", { name: "Answer for Cell biology" });
    expect(JSON.parse(fetchMock.mock.calls.at(-1)![1].body)).toEqual({ course_id: "biology", previous_session_id: "biology-session", reset_learner: false });
    expect(screen.getByRole("switch", { name: /Keep it concise/ }).getAttribute("aria-checked")).toBe("true");
  });

  it("preserves Bayesian snapshots and teaching provenance for an uploaded course, then clears them on course switch", async () => {
    const adapter = readyAdapter();
    const user = await materials(adapter);
    await uploadAndActivate(user);
    const initial = session(biology);
    const returned = { ...fixture, session_id: initial.session_id,
      concepts: initial.concepts.map((c, i) => i ? c : { ...c, mean: 1/3, interval90: { lower: 0.0253, upper: 0.7764 }, evidence_count: 1 }),
      next_question: { ...initial.question, question_id: "biology-q2" },
      decision: { ...fixture.decision, concept_id: initial.question.concept_id },
      tutor: { text: "Returned cell explanation", teaching_source: "bedrock", fallback: false },
    };
    fetchMock.mockResolvedValueOnce(response(returned));
    await user.click(screen.getByRole("radio", { name: "Answer for Cell biology" }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    const impact = await screen.findByRole("region", { name: "What changed?" });
    expect(within(impact).getByRole("row", { name: "Estimate 50.0% 33.3%" })).toBeTruthy();
    expect(within(impact).getByRole("row", { name: "Observations 0 1" })).toBeTruthy();
    expect(within(impact).getByRole("row", { name: "90% uncertainty range 5.0% – 95.0% 2.5% – 77.6%" })).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Read explanation" }));
    expect(screen.getByRole("region", { name: "Study conversation" }).textContent).toContain("AI-generated teaching");
    await user.type(screen.getByRole("textbox", { name: "Your message" }), "old course draft");
    await user.click(screen.getByRole("tab", { name: "Materials" }));
    vi.mocked(adapter.upload).mockResolvedValueOnce({ status: "ready", course: chemistry });
    await user.click(screen.getByRole("button", { name: "Prepare another course" }));
    await user.click(screen.getByRole("button", { name: "Upload course" }));
    await user.click(await screen.findByRole("button", { name: "Activate course" }));
    await screen.findByRole("radio", { name: "Answer for Chemical bonds" });
    expect(document.body.textContent).not.toMatch(/Cell membranes|Osmosis|Returned cell explanation|Intro AI/);
    await user.click(screen.getByRole("tab", { name: "Chatbot" }));
    expect((screen.getByRole("textbox", { name: "Your message" }) as HTMLTextAreaElement).value).toBe("");
    await user.click(screen.getByRole("tab", { name: "Materials" }));
    await user.click(screen.getByRole("button", { name: "Use demo course" }));
    await screen.findByRole("radio", { name: demo.question.choices[0].text });
    expect(JSON.parse(fetchMock.mock.calls.at(-1)![1].body)).toEqual({});
    expect(screen.getByRole("tabpanel", { name: "Study desk" }).textContent).not.toContain("Chemical bonds");
  });

  it("does not fall back to demo after a missing-course restart", async () => {
    const user = await materials(readyAdapter());
    await uploadAndActivate(user);
    fetchMock.mockResolvedValueOnce(response({ detail: "private stack trace" }, 404));
    await user.click(screen.getByRole("button", { name: "New practice session" }));
    expect((await screen.findByRole("alert")).textContent).toContain("course is no longer available");
    expect(document.body.textContent).not.toContain("private stack trace");
    expect(JSON.parse(fetchMock.mock.calls.at(-1)![1].body)).toEqual({ course_id: "biology", previous_session_id: "biology-session", reset_learner: false });
    expect(screen.getByRole("radio", { name: "Answer for Cell biology" }).closest("fieldset")?.disabled).toBe(true);
  });

  it("handles a course disappearing during a turn without grading or leaking errors", async () => {
    const user = await materials(readyAdapter());
    await uploadAndActivate(user);
    fetchMock.mockResolvedValueOnce(response({ detail: "internal implementation" }, 404));
    await user.click(screen.getByRole("radio", { name: "Answer for Cell biology" }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    expect((await screen.findByRole("alert")).textContent).toContain("course is no longer available");
    expect(screen.queryByRole("region", { name: "What changed?" })).toBeNull();
    expect(document.body.textContent).not.toContain("internal implementation");
  });

  it("does not confuse an uploaded course whose ID is demo with the built-in demo", async () => {
    const uploaded = { ...biology, course_id: "demo" };
    const user = await materials(readyAdapter(uploaded));
    fetchMock.mockResolvedValueOnce(response(session(uploaded)));
    await uploadAndActivate(user);
    expect(JSON.parse(fetchMock.mock.calls.at(-1)![1].body)).toEqual({ course_id: "demo" });
    expect(screen.getByRole("tabpanel", { name: "Study desk" }).textContent).not.toContain(demo.question.prompt);
  });

  it("rejects mismatched course/session responses instead of displaying demo questions", async () => {
    const user = await materials(readyAdapter());
    await user.upload(screen.getByLabelText("Add materials to workspace"), pdf());
    await user.click(screen.getByRole("button", { name: "Upload course" }));
    fetchMock.mockResolvedValueOnce(response(demo));
    await user.click(await screen.findByRole("button", { name: "Activate course" }));
    await screen.findByRole("alert");
    expect(screen.queryByRole("radio")).toBeNull();
    expect(screen.getByRole("tabpanel", { name: "Study desk" }).textContent).not.toContain(demo.question.prompt);
  });

  it("ignores an old turn that finishes after switching courses", async () => {
    const user = await materials(readyAdapter());
    const oldTurn = deferred<ReturnType<typeof response>>();
    await user.click(screen.getByRole("tab", { name: "Study desk" }));
    fetchMock.mockReturnValueOnce(oldTurn.promise);
    await user.click(screen.getByRole("radio", { name: demo.question.choices[0].text }));
    await user.click(screen.getByRole("button", { name: "Check answer" }));
    await user.click(screen.getByRole("tab", { name: "Materials" }));
    await uploadAndActivate(user);
    await act(async () => oldTurn.resolve(response({ ...fixture, session_id: demo.session_id })));
    expect(screen.getByRole("radio", { name: "Answer for Cell biology" })).toBeTruthy();
    expect(screen.queryByRole("region", { name: "What changed?" })).toBeNull();
    expect(document.body.textContent).not.toContain(fixture.tutor.text);
  });
});

describe("API adapter and public source seam", () => {
  it("uses multipart uploads and explicit public projection", async () => {
    fetchMock.mockResolvedValueOnce(response({ ...biology, answer_key: "secret" }, 201));
    const result = await createCourseUploadAdapter().upload([pdf(), new File(["slides"], "slides.pptx")], " Biology ");
    const [path, options] = fetchMock.mock.calls[0];
    expect(path).toBe("/api/v1/courses");
    expect(options.body).toBeInstanceOf(FormData);
    expect(options.body.getAll("files")).toHaveLength(2);
    expect(options.body.get("title")).toBe("Biology");
    expect(options.headers).toBeUndefined(); // Browser sets the multipart boundary.
    expect(result).toEqual({ status: "ready", course: biology });
  });
  it.each([[413, "too_large"], [415, "unsupported"], [422, "processing"], [503, "service"], [404, "unavailable"], [202, "service"], [200, "service"], [400, "invalid_files"]])("maps HTTP %s without showing private detail", async (status, code) => {
    fetchMock.mockResolvedValueOnce(response({ detail: "private provider data" }, status as number));
    await expect(createCourseUploadAdapter().upload([pdf()], "Biology")).rejects.toEqual(new CourseError(code as ConstructorParameters<typeof CourseError>[0]));
  });
  it.each([undefined, "", "   "])("omits an optional blank title (%s)", async title => {
    fetchMock.mockResolvedValueOnce(response(biology, 201));
    await createCourseUploadAdapter().upload([pdf()], title);
    expect(fetchMock.mock.calls[0][1].body.has("title")).toBe(false);
  });
  it.each([200, 202])("does not activate a course from unexpected HTTP %s", async status => {
    const user = await materials();
    fetchMock.mockResolvedValueOnce(response(biology, status));
    await user.upload(screen.getByLabelText("Add materials to workspace"), pdf());
    await user.click(screen.getByRole("button", { name: "Upload course" }));
    await screen.findByRole("alert");
    expect(screen.queryByRole("button", { name: "Activate course" })).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it("rejects malformed metadata and duplicate concept IDs", () => {
    expect(() => publicCourse({ ...biology, concepts: [biology.concepts[0], biology.concepts[0]] })).toThrow(CourseError);
    expect(() => publicCourse({ ...biology, question_count: 0 })).toThrow(CourseError);
  });
  it("requires metadata-matching estimates in uploaded sessions", async () => {
    fetchMock.mockResolvedValueOnce(response({ ...session(biology), concepts: demo.concepts }));
    await expect(createSession(biology)).rejects.toThrow(CourseError);
  });
  it("renders no invented source; only supplied public filenames and locations", () => {
    const view = render(<QuestionSource />);
    expect(screen.queryByLabelText("Question source")).toBeNull();
    view.rerender(<QuestionSource source={{ filename: "cells.pdf", page: 3 }} />);
    expect(screen.getByLabelText("Question source").textContent).toBe("Source: cells.pdf · page 3");
  });
});
