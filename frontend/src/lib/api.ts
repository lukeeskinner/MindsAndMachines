import { getIdToken } from "../auth/cognito";

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
    const payload = await response.json().catch(() => null);
    throw new Error(
      typeof payload?.detail === "string"
        ? payload.detail
        : "We couldn’t complete that request. Start a new session to try again.",
    );
  }
  return response.json();
}
