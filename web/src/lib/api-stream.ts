// Streaming-aware client for /pages/ai/chat.
//
// EventSource can't POST or set custom headers. We use Microsoft's
// fetch-event-source which gives us POST + AbortController + custom
// headers while preserving SSE framing semantics.

import { fetchEventSource } from "@microsoft/fetch-event-source";

import type {
  ChatRequestBody,
  SSEDoneData,
  SSEErrorData,
  SSETextData,
  SSEToolCallData,
  SSEWarningData,
  ToolCall,
} from "./ai-chat-types";
import { apiUrl } from "./base-path";

export interface StreamChatHandlers {
  onText?: (delta: string) => void;
  onToolCall?: (call: ToolCall) => void;
  onWarning?: (message: string) => void;
  onError?: (message: string) => void;
  onDone?: (info: SSEDoneData) => void;
}

/**
 * POST to /pages/ai/chat and forward SSE events to handlers.
 *
 * Returns when the stream closes cleanly OR is aborted via the
 * supplied signal. Non-2xx HTTP responses surface through `onError`.
 *
 * fetchEventSource calls handlers on whatever microtask comes off the
 * fetch — React state updates from inside handlers are batched as
 * normal.
 */
export async function streamChat(
  body: ChatRequestBody,
  handlers: StreamChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const ctrl = new AbortController();
  const onAbort = () => ctrl.abort();
  if (signal) {
    if (signal.aborted) {
      ctrl.abort();
    } else {
      signal.addEventListener("abort", onAbort, { once: true });
    }
  }

  try {
    await fetchEventSource(apiUrl("/pages/ai/chat"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
      signal: ctrl.signal,
      // Don't reconnect on transient errors — chat completions are
      // not resumable. Surface the failure once and let the user
      // decide whether to retry.
      openWhenHidden: true,
      async onopen(response) {
        if (response.ok) {
          const ct = response.headers.get("content-type") || "";
          if (!ct.includes("text/event-stream")) {
            handlers.onError?.(`Unexpected response type: ${ct || "(none)"}`);
            ctrl.abort();
          }
          return;
        }
        // Try to surface the server's JSON error detail.
        let detail: string | null = null;
        try {
          const json = await response.json();
          if (json && typeof json.detail === "string") {
            detail = json.detail;
          }
        } catch {
          /* ignore — fall through */
        }
        handlers.onError?.(detail ?? `Server returned ${response.status}.`);
        ctrl.abort();
      },
      onmessage(ev) {
        if (!ev.event) return;
        let data: unknown;
        try {
          data = JSON.parse(ev.data);
        } catch {
          return;
        }
        switch (ev.event) {
          case "text":
            handlers.onText?.((data as SSETextData).delta);
            break;
          case "tool_call": {
            const td = data as SSEToolCallData;
            handlers.onToolCall?.({
              id: td.id,
              op: td.op,
              args: td.args,
            } as ToolCall);
            break;
          }
          case "warning":
            handlers.onWarning?.((data as SSEWarningData).message);
            break;
          case "error":
            handlers.onError?.((data as SSEErrorData).message);
            ctrl.abort();
            break;
          case "done":
            handlers.onDone?.(data as SSEDoneData);
            ctrl.abort();
            break;
        }
      },
      onerror(err) {
        // The default behavior reconnects forever; we want to surface
        // and stop. Throw to terminate the stream.
        const msg = err instanceof Error ? err.message : "Stream connection failed.";
        // AbortError is expected when we close cleanly — don't surface.
        if (err instanceof DOMException && err.name === "AbortError") {
          throw err;
        }
        handlers.onError?.(msg);
        throw err;
      },
    });
  } catch (err) {
    // Swallow user-initiated aborts; rethrow anything else so callers
    // can attach their own catch if they want.
    if (err instanceof DOMException && err.name === "AbortError") {
      return;
    }
    // We've already surfaced via onError; absorb so callers don't see
    // a double notification.
  } finally {
    if (signal) {
      signal.removeEventListener("abort", onAbort);
    }
  }
}
