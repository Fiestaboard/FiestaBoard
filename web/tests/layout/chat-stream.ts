// Deterministic SSE responses exercise the real transport without a backend.
import type { ChatRequestBody, ToolCall } from "@/lib/ai-chat-types";
import type { StreamChatHandlers } from "@/lib/api-stream";

export async function streamChat(
  _body: ChatRequestBody,
  handlers: StreamChatHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const scenario = new URLSearchParams(window.location.search).get("scenario") ?? "complete";
  if (scenario === "thinking") {
    handlers.onStatus?.({ phase: "thinking", message: "Thinking", tool_call_id: null, step: 0 });
    await new Promise<void>((resolve) => signal?.addEventListener("abort", () => resolve(), { once: true }));
    return;
  }
  const call: ToolCall = {
    id: "layout-call",
    name: "get_page",
    title: "Read page",
    args: { page_id: "sunset" },
    read_only: true,
    destructive: false,
    requires_approval: false,
    source: "mcp",
  };
  const done = {
    model_used: "example-model",
    provider_id: "example",
    usage: { prompt_tokens: 10, completion_tokens: 10, total_tokens: 20 },
    steps: 1,
  };
  if (scenario === "approval") {
    const deletion = {
      ...call,
      name: "delete_page",
      title: "Delete page",
      read_only: false,
      destructive: true,
      requires_approval: true,
    };
    handlers.onToolCall?.(deletion);
    handlers.onDone?.({ ...done, reason: "awaiting_approval", pending_tool_call_id: deletion.id });
    return;
  }
  handlers.onToolCall?.(call);
  handlers.onToolResult?.({
    id: call.id,
    name: call.name,
    status: "ok",
    summary: "Read the sunset page",
    result: { name: "Sunset", template: ["SUNSET", "GOLDEN HOUR"] },
    error: null,
  });
  const create = {
    ...call,
    id: "layout-create",
    name: "create_page",
    title: "Create page",
    args: {
      name: "Golden hour",
      template_lines: [
        "",
        "{65}{65}{66}{66}{66}{66}{65}{65}",
        "{65}{66}{66}{67}{67}{66}{66}{65}",
        "{66}{66}{67}{67}{67}{67}{66}{66}",
        "GOLDEN HOUR",
        "",
      ],
    },
    read_only: false,
  };
  handlers.onToolCall?.(create);
  handlers.onToolResult?.({
    id: create.id,
    name: create.name,
    status: "ok",
    summary: "Created Golden hour",
    result: { page_id: "golden", message: "Page created." },
    error: null,
  });
  handlers.onText?.(
    "Your **Golden hour** page is ready.\n\nA warm sunset, a quiet horizon, and space to breathe. Open the preview to make it yours.",
  );
  handlers.onDone?.({ ...done, steps: 2, reason: "complete", pending_tool_call_id: null });
}

export function chatResponse(signal?: AbortSignal | null): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      let closed = false;
      const close = () => {
        if (!closed) {
          closed = true;
          controller.close();
        }
      };
      const event = (name: string, data: unknown) => {
        if (!closed) controller.enqueue(encoder.encode(`event: ${name}\ndata: ${JSON.stringify(data)}\n\n`));
      };
      signal?.addEventListener("abort", close, { once: true });
      void streamChat(
        {} as ChatRequestBody,
        {
          onStatus: (data) => event("status", data),
          onToolCall: (data) => event("tool_call", data),
          onToolResult: (data) => event("tool_result", data),
          onText: (delta) => event("text", { delta }),
          onDone: (data) => {
            event("done", data);
            close();
          },
        },
        signal ?? undefined,
      ).finally(() => signal?.removeEventListener("abort", close));
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}
