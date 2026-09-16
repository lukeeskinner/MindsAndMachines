export async function post<T>(path: string, body: object, authHeader?: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (authHeader) headers.Authorization = authHeader;
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
