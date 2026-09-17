import { getIdToken } from "../auth/cognito";

class RequestError extends Error {}
export function requestErrorMessage(error: unknown) {
  return error instanceof RequestError ? error.message : "The learning service is unavailable. Please try again.";
}

export async function post<T>(path: string, body: object): Promise<T> {
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
  const response = await fetch(`/api/v1/${path}`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(20000),
  });
  if (!response.ok) {
    // Do not surface raw exceptions or unreviewed server detail strings.
    const uploaded = path === "sessions" && "course_id" in body;
    const message = uploaded && response.status === 404
      ? "This course is no longer available. The service may have restarted. Upload the materials again or choose the demo."
      : path === "turns" && response.status === 409
        ? "Study for this uploaded course is not available yet. Your course has not been graded."
        : response.status === 401 || response.status === 403
          ? "Please sign in again to continue."
          : "We couldn’t complete that request. Start a new session to try again.";
    throw new RequestError(message);
  }
  return response.json();
}
