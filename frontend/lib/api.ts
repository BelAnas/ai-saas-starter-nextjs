// Browser-side calls to the API. They go to /api/... on the same origin; the Next.js server
// forwards them (see app/api/[...path]/route.ts), so the session cookie needs no CORS setup.

import { createSseParser } from "./sse";
import type { Quota } from "./types";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

async function toError(response: Response): Promise<ApiError> {
  let body: Record<string, unknown> = {};
  try {
    body = await response.json();
  } catch {
    // not JSON: keep the empty body
  }
  const detail = body.detail;
  const message =
    typeof detail === "string"
      ? detail
      : Array.isArray(detail) && detail[0]?.msg
        ? String(detail[0].msg) // FastAPI validation errors are a list
        : `Request failed (${response.status}).`;
  return new ApiError(response.status, message, body);
}

export async function api<T>(path: string, init: { method?: string; json?: unknown } = {}): Promise<T> {
  const response = await fetch(path, {
    method: init.method ?? (init.json === undefined ? "GET" : "POST"),
    headers: init.json === undefined ? undefined : { "Content-Type": "application/json" },
    body: init.json === undefined ? undefined : JSON.stringify(init.json),
    cache: "no-store",
  });
  if (!response.ok) throw await toError(response);
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export type StreamMeta = { conversation_id: number; title: string; is_new: boolean; model: string };
export type StreamEnd = {
  message_id: number | null;
  status: string;
  quota: Quota | null;
  usage: { input_tokens: number; output_tokens: number; estimated: boolean; cost_usd: number };
  detail?: string;
};

export type StreamHandlers = {
  onMeta: (meta: StreamMeta) => void;
  onDelta: (text: string) => void;
  onDone: (end: StreamEnd) => void;
  onError: (end: StreamEnd) => void;
};

/** Send a message and call the handlers as the answer arrives. Abort the signal to stop. */
export async function streamChat(
  body: { message: string; conversation_id: number | null },
  handlers: StreamHandlers,
  signal: AbortSignal,
): Promise<void> {
  const response = await fetch("/api/chat/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok || !response.body) throw await toError(response);

  const parser = createSseParser(({ event, data }) => {
    const payload = JSON.parse(data);
    if (event === "meta") handlers.onMeta(payload);
    else if (event === "delta") handlers.onDelta(payload.text);
    else if (event === "done") handlers.onDone(payload);
    else if (event === "error") handlers.onError(payload);
  });
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    parser.push(value);
  }
}
