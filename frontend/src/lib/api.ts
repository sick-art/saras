const BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
    this.name = "ApiError"
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}/api${path}`, {
    headers: { "Content-Type": "application/json", ...init?.headers },
    ...init,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new ApiError(res.status, text)
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body) }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: (path: string) => request<void>(path, { method: "DELETE" }),
}

// ── SSE helper — returns an EventSource-like async cleanup ────────────────────
// Returns a stop() function. Caller must call stop() to close the connection.
export function streamEvalRun(
  projectId: string,
  runId: string,
  onEvent: (event: import("@/types/eval").EvalProgressEvent) => void,
  onError?: (err: Error) => void,
): () => void {
  const url = `${BASE_URL}/api/projects/${projectId}/evals/runs/${runId}/stream`
  const es = new EventSource(url)

  es.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data) as import("@/types/eval").EvalProgressEvent
      onEvent(data)
      if (data.type === "complete" || data.type === "error") {
        es.close()
      }
    } catch {
      // ignore parse errors
    }
  }

  es.onerror = () => {
    es.close()
    onError?.(new Error("SSE connection error"))
  }

  return () => es.close()
}

export { ApiError }
