import { getIdToken } from "../auth/cognito";
import { withRequestTimeout } from "./requestTimeout";

export class RequestError extends Error {}
export function requestErrorMessage(error: unknown) {
  return error instanceof RequestError ? error.message : "The request could not be completed. Please retry.";
}

export async function post<T>(path: string, body: object): Promise<T> {
  let stage: "prepare" | "request" | "response" = "prepare";
  return withRequestTimeout(20000, async signal => {
    try {
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      // Creation and reset use the same supported authenticated route. Read the
      // current token for each request; keep existing token storage unchanged.
      // /turns does not yet verify Authorization or enforce session ownership.
      if (path === "sessions") {
        const token = getIdToken();
        if (token) headers.Authorization = `Bearer ${token}`;
      }
      const serialized = JSON.stringify(body);
      stage = "request";
      const response = await fetch(`/api/v1/${path}`, {
        method: "POST",
        headers,
        body: serialized,
        signal,
      });
      stage = "response";
      if (!response.ok) {
        // Do not surface raw exceptions or unreviewed server detail strings.
        const uploaded = path === "sessions" && "course_id" in body;
        const message = path === "focus-practice"
          ? "Focus practice could not start. Your learner model is preserved; please retry."
          : uploaded && response.status === 404
          ? "This course is no longer available. The service may have restarted. Upload the materials again or choose the demo."
          : (path === "turns" || path === "chat") && response.status === 404
            ? "This session or its course is no longer available. Start a new session; if the course is missing, upload the materials again."
            : path === "chat" && response.status === 409
              ? "Another request is still running. Wait a moment, then send again."
              : path === "chat" && response.status >= 500
                ? "The tutor is temporarily unavailable. Your draft is saved; please retry."
            : response.status === 401 || response.status === 403
              ? "Please sign in again to continue."
              : "We couldn’t complete that request. Start a new session to try again.";
        throw new RequestError(message);
      }
      return await response.json();
    } catch (error) {
      const reason = error instanceof RequestError ? "http" : signal.aborted ? "timeout" : stage;
      // Fixed diagnostics only: no message bodies, session IDs, tokens or raw errors.
      console.warn("learning_request_failed", { path, reason });
      if (error instanceof RequestError) throw error;
      throw new RequestError(signal.aborted
        ? "The request timed out. Please retry."
        : stage === "prepare"
          ? "The request could not be prepared in this browser. Please reload and retry."
          : stage === "request"
            ? "Could not reach the learning service. Check your connection and retry."
            : "The learning service returned an invalid response. Please retry.");
    }
  });
}
