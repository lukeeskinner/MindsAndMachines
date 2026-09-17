// AbortController works in engines that do not implement AbortSignal.timeout.
// Keep the deadline active through response parsing, and release it on all paths.
export async function withRequestTimeout<T>(milliseconds: number, request: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), milliseconds);
  try {
    return await request(controller.signal);
  } finally {
    clearTimeout(timer);
  }
}
