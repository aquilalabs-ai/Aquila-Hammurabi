const BASE = "/api";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

async function request<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
      ...init.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export function get<T>(path: string): Promise<T> {
  return request<T>(path);
}

export function post<T>(path: string, body?: unknown, headers?: HeadersInit): Promise<T> {
  const isFormData = body instanceof FormData;
  return request<T>(path, {
    method: "POST",
    body: isFormData ? body : JSON.stringify(body),
    headers: isFormData ? {} : { "Content-Type": "application/json", ...headers },
  });
}

export function del<T = void>(path: string): Promise<T> {
  return request<T>(path, { method: "DELETE" });
}

export function sseStream(
  path: string,
  body: unknown,
  onToken: (text: string) => void,
  onDone: () => void,
  onError: (err: string) => void,
): () => void {
  const controller = new AbortController();

  (async () => {
    const res = await fetch(`${BASE}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!res.ok || !res.body) {
      const body = await res.text().catch(() => res.statusText);
      onError(`${res.status}: ${body || res.statusText}`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() ?? "";
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const data = line.slice(6).trim();
        if (data === "[DONE]") {
          onDone();
          return;
        }
        try {
          const evt = JSON.parse(data);
          if (evt.type === "token" && evt.content) onToken(evt.content);
          if (evt.type === "error") onError(evt.message ?? evt.detail ?? "Stream error");
        } catch {
          // ignore parse errors
        }
      }
    }
    onDone();
  })().catch((err: unknown) => {
    if (err instanceof Error && err.name !== "AbortError") onError(err.message);
  });

  return () => controller.abort();
}
