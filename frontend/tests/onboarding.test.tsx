// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RootApp } from "../src/RootApp";
import {
  initialDraft,
  selectFiles,
  validateDraft,
  MAX_FILE_BYTES,
} from "../src/components/onboarding/model";
import fixture from "../../contracts/fixtures/turn_response.json";

let fetchMock = vi.fn();
beforeEach(() => {
  window.history.replaceState(null, "", "/");
  window.sessionStorage.clear();
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
  Element.prototype.scrollIntoView = vi.fn();
  fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      session_id: "setup-demo",
      question: fixture.next_question,
      concepts: fixture.concepts,
    }),
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

async function signIn() {
  const user = userEvent.setup({ applyAccept: false });
  await user.type(
    screen.getByRole("textbox", { name: "Email" }),
    "alex@example.com",
  );
  await user.type(screen.getByLabelText("Password"), "correcthorsebattery");
  await user.click(screen.getByRole("button", { name: "Continue to setup" }));
  await screen.findByRole("heading", { name: "Let’s set up your course." });
  return user;
}

describe("course onboarding", () => {
  it("gates setup and study behind the frontend Cognito sign-in screen", async () => {
    window.history.replaceState(null, "", "/#/study");
    const user = userEvent.setup();
    render(<RootApp />);
    expect(
      screen.getByRole("heading", { name: "Sign in to your study workspace." }),
    ).toBeTruthy();
    expect(window.location.hash).toBe("#/study");
    await user.click(screen.getByRole("button", { name: "Continue to setup" }));
    expect(screen.getByText("Enter your email.")).toBeTruthy();
    await user.type(
      screen.getByRole("textbox", { name: "Email" }),
      "alex@example.com",
    );
    await user.type(screen.getByLabelText("Password"), "correcthorsebattery");
    await user.click(screen.getByRole("button", { name: "Continue to setup" }));
    await screen.findByRole("heading", { name: "Let’s set up your course." });
    expect(window.location.hash).toBe("#/setup");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("validates required course/date fields, then reviews a local draft without a server request", async () => {
    render(<RootApp />);
    const user = await signIn();
    const course = screen.getByRole("textbox", { name: "Course name" });
    await user.clear(course);
    await user.click(screen.getByRole("button", { name: "Review my setup" }));
    expect(screen.getByText("Add a course name to continue.")).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(course));
    await user.type(course, "Graph search seminar");
    await user.click(screen.getByRole("button", { name: "Review my setup" }));
    expect(
      screen.getByText("Choose your exam date, or select a different goal."),
    ).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Exam date"), {
      target: { value: "2099-10-05" },
    });
    await user.selectOptions(
      screen.getByRole("combobox", { name: "How much time can you study?" }),
      "3",
    );
    await user.click(screen.getByRole("button", { name: "Review my setup" }));
    await screen.findByRole("heading", { name: "Your course setup is ready." });
    expect(
      screen.getByRole("heading", { name: "Graph search seminar" }),
    ).toBeTruthy();
    expect(screen.getByText("3 hours total")).toBeTruthy();
    expect(screen.getByText("Add them later")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("allows a goal with no deadline and preserves edited details after reviewing", async () => {
    render(<RootApp />);
    const user = await signIn();
    await user.click(
      screen.getByRole("radio", { name: /Build understanding/ }),
    );
    await user.click(screen.getByRole("button", { name: "Review my setup" }));
    await screen.findByRole("heading", { name: "Your course setup is ready." });
    expect(screen.getByText("No date set")).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Edit setup" }));
    expect(
      (
        screen.getByRole("radio", {
          name: /Build understanding/,
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("6");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("supports file selection, useful validation, removal, and drag-and-drop without uploading", async () => {
    render(<RootApp />);
    const user = await signIn();
    const file = new File(["notes"], "lecture.pdf", {
      type: "application/pdf",
      lastModified: 1,
    });
    const unsupported = new File(["text"], "archive.zip", {
      type: "application/zip",
    });
    const empty = new File([], "empty.pdf", { type: "application/pdf" });
    const big = new File(["big"], "oversize.pdf", { type: "application/pdf" });
    Object.defineProperty(big, "size", { value: MAX_FILE_BYTES + 1 });
    await user.upload(screen.getByLabelText("Choose course materials"), [
      file,
      unsupported,
      empty,
      big,
    ]);
    const list = screen.getByRole("list", {
      name: "Selected course materials",
    });
    expect(within(list).getByText("lecture.pdf")).toBeTruthy();
    expect(screen.getByText(/archive.zip: choose a PDF/)).toBeTruthy();
    expect(screen.getByText(/empty.pdf: this file is empty/)).toBeTruthy();
    expect(screen.getByText(/oversize.pdf: the maximum/)).toBeTruthy();
    await user.upload(screen.getByLabelText("Choose course materials"), file);
    expect(screen.getByText("lecture.pdf is already selected.")).toBeTruthy();
    await user.click(
      screen.getByRole("button", { name: "Remove lecture.pdf" }),
    );
    expect(
      screen.queryByRole("list", { name: "Selected course materials" }),
    ).toBeNull();
    fireEvent.drop(
      screen
        .getByText("Drop in a little context.")
        .closest(".material-dropzone")!,
      { dataTransfer: { files: [file] } },
    );
    expect(
      screen.getByRole("button", { name: "Remove lecture.pdf" }),
    ).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("keeps the draft and practice session when moving between setup and the study desk", async () => {
    render(<RootApp />);
    const user = await signIn();
    const course = screen.getByRole("textbox", { name: "Course name" });
    await user.clear(course);
    await user.type(course, "My AI course");
    const file = new File(["notes"], "my-notes.txt", { type: "text/plain" });
    await user.upload(screen.getByLabelText("Choose course materials"), file);
    await user.click(
      screen.getByRole("button", { name: "Open practice demo" }),
    );
    await screen.findByRole("radio", {
      name: "Admissible, but not consistent.",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({});
    await user.click(screen.getByRole("link", { name: /Skip to/ }));
    await waitFor(() => expect(window.location.hash).toBe("#workspace"));
    expect(screen.getByRole("button", { name: "Course setup" })).toBeTruthy();
    await user.click(
      screen.getByRole("radio", { name: "Admissible, but not consistent." }),
    );
    await user.click(screen.getByRole("button", { name: "Course setup" }));
    expect(
      (screen.getByRole("textbox", { name: "Course name" }) as HTMLInputElement)
        .value,
    ).toBe("My AI course");
    expect(
      screen.getByRole("button", { name: "Remove my-notes.txt" }),
    ).toBeTruthy();
    await user.click(
      screen.getByRole("button", { name: "Open practice demo" }),
    );
    expect(
      (
        screen.getByRole("radio", {
          name: "Admissible, but not consistent.",
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("edits workspace materials and goals locally while preserving practice and sharing setup state", async () => {
    render(<RootApp />);
    const user = await signIn();
    await user.upload(
      screen.getByLabelText("Choose course materials"),
      new File(["notes"], "lecture.txt"),
    );
    await user.click(
      screen.getByRole("button", { name: "Open practice demo" }),
    );
    const answer = await screen.findByRole("radio", {
      name: "Admissible, but not consistent.",
    });
    await user.click(answer);
    await user.click(screen.getByRole("tab", { name: "Chatbot" }));
    await user.click(screen.getByRole("button", { name: "Manage materials" }));
    expect(
      screen.getByRole("button", { name: "Remove lecture.txt" }),
    ).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Edit course goals" }));
    const name = screen.getByRole("textbox", { name: "Course name" });
    await user.clear(name);
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(screen.getByText("Add a course name to continue.")).toBeTruthy();
    await waitFor(() => expect(document.activeElement).toBe(name));
    await user.type(name, "Algorithms seminar");
    await user.selectOptions(screen.getByLabelText("Study goal"), "understand");
    await user.selectOptions(
      screen.getByLabelText("Study time available"),
      "3",
    );
    // File changes during editing must not be overwritten by saving goal fields.
    await user.upload(
      screen.getByLabelText("Add materials to workspace"),
      new File(["reading"], "reading.md"),
    );
    await user.click(
      screen.getByRole("button", { name: "Remove lecture.txt" }),
    );
    await user.click(screen.getByRole("button", { name: "Save changes" }));
    expect(screen.getByText("Changes saved in this tab.")).toBeTruthy();
    expect(screen.getByText("Algorithms seminar")).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "Remove reading.md" }),
    ).toBeTruthy();
    await user.click(screen.getByRole("button", { name: "Edit course goals" }));
    await user.clear(screen.getByRole("textbox", { name: "Course name" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByText("Algorithms seminar")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "Study desk" }));
    expect(
      (
        screen.getByRole("radio", {
          name: "Admissible, but not consistent.",
        }) as HTMLInputElement
      ).checked,
    ).toBe(true);
    await user.click(screen.getByRole("button", { name: "Course setup" }));
    expect(
      (screen.getByRole("textbox", { name: "Course name" }) as HTMLInputElement)
        .value,
    ).toBe("Algorithms seminar");
    expect((screen.getByRole("combobox") as HTMLSelectElement).value).toBe("3");
    expect(
      screen.getByRole("button", { name: "Remove reading.md" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Remove lecture.txt" }),
    ).toBeNull();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/sessions");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({});
  });

  it("limits the local file collection and rejects past dates", () => {
    const incoming = Array.from(
      { length: 9 },
      (_, i) => new File(["content"], `${i}.pdf`),
    );
    const result = selectFiles([], incoming);
    expect(result.files).toHaveLength(8);
    expect(result.errors).toEqual([
      "You can select up to 8 files. Remove a file to add another.",
    ]);
    expect(
      validateDraft({ ...initialDraft(), examDate: "2000-01-01" }).examDate,
    ).toBe("Choose today or a future date.");
  });
});
