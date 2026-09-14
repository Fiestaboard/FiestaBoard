import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ChatMessage, ToolCall, ToolResult } from "@/lib/ai-chat-types";
import type * as apiStreamModule from "@/lib/api-stream";
import { computeAppliedSnapshot, toWireMessages, useAiChat } from "@/lib/use-ai-chat";

// Control streamChat from tests via captured references.
let capturedHandlers: Parameters<(typeof apiStreamModule)["streamChat"]>[1] | null = null;
let capturedBodies: unknown[] = [];
let resolveStream: (() => void) | null = null;

vi.mock("@/lib/api-stream", () => ({
  streamChat: vi.fn(
    (body: unknown, handlers: unknown, _signal?: unknown) =>
      new Promise<void>((resolve) => {
        capturedBodies.push(body);
        capturedHandlers = handlers as any;
        resolveStream = resolve;
      }),
  ),
}));

function makeOpts(overrides: Partial<Parameters<typeof useAiChat>[0]> = {}) {
  return {
    getTurnContext: () => ({ deviceType: "flagship" as const, surface: "global" as const }),
    ...overrides,
  };
}

const CREATE_PAGE: ToolCall = {
  id: "tc1",
  name: "create_page",
  args: { name: "Morning", template_lines: ["HELLO", "WORLD"] },
  title: "Create page",
  read_only: false,
  destructive: false,
  requires_approval: false,
  source: "mcp",
};

const DELETE_PAGE: ToolCall = {
  ...CREATE_PAGE,
  id: "tc2",
  name: "delete_page",
  args: { page_id: "p1" },
  title: "Delete page",
  destructive: true,
  requires_approval: true,
};

const OK: ToolResult = { id: "tc1", name: "create_page", status: "ok", summary: "Page created.", result: { page_id: "p9" }, error: null };

const DONE = { model_used: "m", provider_id: "p", usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 }, steps: 1 };

function lastBody() {
  return capturedBodies[capturedBodies.length - 1] as { messages: unknown[]; resume?: unknown };
}

beforeEach(() => {
  capturedHandlers = null;
  capturedBodies = [];
  resolveStream = null;
  vi.clearAllMocks();
});

describe("useAiChat", () => {
  it("starts with idle status, empty messages, and no error", () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    expect(result.current.status).toBe("idle");
    expect(result.current.messages).toHaveLength(0);
    expect(result.current.error).toBeNull();
    expect(result.current.pendingApproval).toBeNull();
  });

  it("send() adds the user message immediately and streams", () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hello");
    });
    expect(result.current.messages[0]).toMatchObject({ role: "user", content: "hello" });
    expect(result.current.status).toBe("streaming");
    const last = result.current.messages[result.current.messages.length - 1];
    expect(last).toMatchObject({ role: "assistant", pending: true });
    expect(lastBody().messages).toEqual([{ role: "user", content: "hello" }]);
    expect(lastBody().resume).toBeUndefined();
  });

  it("send() trims whitespace and ignores blank input", () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("   ");
    });
    expect(result.current.messages).toHaveLength(0);
  });

  it("text deltas append to the in-flight assistant message", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      capturedHandlers?.onText?.("Hel");
      capturedHandlers?.onText?.("lo");
    });
    expect(result.current.messages[1].content).toBe("Hello");
  });

  it("a tool_call attaches a running card with a board preview and fires the callback", async () => {
    const onToolCall = vi.fn();
    const { result } = renderHook(() => useAiChat(makeOpts({ onToolCall })));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      capturedHandlers?.onToolCall?.(CREATE_PAGE);
    });
    const card = result.current.messages[1].toolCalls![0];
    expect(card.phase).toBe("running");
    expect(card.appliedSnapshot?.template).toEqual(["HELLO", "WORLD"]);
    expect(onToolCall).toHaveBeenCalledWith(CREATE_PAGE);
  });

  it("a tool_result settles the matching card and fires the callback with the call", async () => {
    const onToolResult = vi.fn();
    const { result } = renderHook(() => useAiChat(makeOpts({ onToolResult })));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      capturedHandlers?.onToolCall?.(CREATE_PAGE);
      capturedHandlers?.onToolResult?.(OK);
    });
    const card = result.current.messages[1].toolCalls![0];
    expect(card.phase).toBe("ok");
    expect(card.result).toEqual(OK);
    expect(onToolResult).toHaveBeenCalledWith(OK, CREATE_PAGE);
  });

  it("status frames set the turn's status line and clear it on a result", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      capturedHandlers?.onStatus?.({ phase: "tool_running", message: "Running create_page…", tool_call_id: "tc1", step: 1 });
    });
    expect(result.current.messages[1].statusMessage).toBe("Running create_page…");
    await act(async () => {
      capturedHandlers?.onToolCall?.(CREATE_PAGE);
      capturedHandlers?.onToolResult?.(OK);
    });
    expect(result.current.messages[1].statusMessage).toBeUndefined();
  });

  it("done{awaiting_approval} pauses on the destructive call", async () => {
    const onAwaitingApproval = vi.fn();
    const { result } = renderHook(() => useAiChat(makeOpts({ onAwaitingApproval })));
    act(() => {
      result.current.send("delete it");
    });
    await act(async () => {
      capturedHandlers?.onToolCall?.(DELETE_PAGE);
      capturedHandlers?.onDone?.({ ...DONE, reason: "awaiting_approval", pending_tool_call_id: "tc2" });
      resolveStream?.();
    });
    expect(result.current.status).toBe("awaiting_approval");
    expect(result.current.pendingApproval?.id).toBe("tc2");
    expect(result.current.messages[1].toolCalls![0].phase).toBe("awaiting_approval");
    expect(onAwaitingApproval).toHaveBeenCalledWith(DELETE_PAGE);
  });

  it("approve() re-POSTs with the decision and keeps appending to the same assistant message", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("delete it");
    });
    await act(async () => {
      capturedHandlers?.onText?.("Deleting.");
      capturedHandlers?.onToolCall?.(DELETE_PAGE);
      capturedHandlers?.onDone?.({ ...DONE, reason: "awaiting_approval", pending_tool_call_id: "tc2" });
      resolveStream?.();
    });
    act(() => {
      result.current.approve("tc2", "approve");
    });
    expect(result.current.status).toBe("streaming");
    expect(result.current.messages).toHaveLength(2); // no new placeholder
    expect(lastBody().resume).toEqual({ tool_call_id: "tc2", decision: "approve" });
    // The replayed transcript carries the pending call; the server answers it.
    expect(lastBody().messages).toEqual([
      { role: "user", content: "delete it" },
      { role: "assistant", content: "Deleting.", tool_calls: [{ id: "tc2", name: "delete_page", args: { page_id: "p1" } }] },
    ]);
    await act(async () => {
      capturedHandlers?.onToolResult?.({ ...OK, id: "tc2", name: "delete_page", summary: "Deleted." });
      capturedHandlers?.onText?.(" Gone.");
      capturedHandlers?.onDone?.({ ...DONE, reason: "complete", pending_tool_call_id: null });
      resolveStream?.();
    });
    expect(result.current.messages[1].content).toBe("Deleting. Gone.");
    expect(result.current.messages[1].toolCalls![0].phase).toBe("ok");
    expect(result.current.status).toBe("idle");
  });

  it("deny is recorded on the card and sent as the decision", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("delete it");
    });
    await act(async () => {
      capturedHandlers?.onToolCall?.(DELETE_PAGE);
      capturedHandlers?.onDone?.({ ...DONE, reason: "awaiting_approval", pending_tool_call_id: "tc2" });
      resolveStream?.();
    });
    act(() => {
      result.current.approve("tc2", "deny");
    });
    expect(lastBody().resume).toEqual({ tool_call_id: "tc2", decision: "deny" });
    expect(result.current.messages[1].toolCalls![0].phase).toBe("denied");
  });

  it("typing while an approval is pending denies it and sends the new message together", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("delete it");
    });
    await act(async () => {
      capturedHandlers?.onToolCall?.(DELETE_PAGE);
      capturedHandlers?.onDone?.({ ...DONE, reason: "awaiting_approval", pending_tool_call_id: "tc2" });
      resolveStream?.();
    });
    act(() => {
      result.current.send("actually rename it");
    });
    expect(lastBody().resume).toEqual({ tool_call_id: "tc2", decision: "deny" });
    const wire = lastBody().messages as Array<{ role: string; content?: string }>;
    expect(wire[wire.length - 1]).toEqual({ role: "user", content: "actually rename it" });
    expect(result.current.pendingApproval).toBeNull();
  });

  it("a question pauses the turn, and the composer answers it", async () => {
    const onElicitation = vi.fn();
    const { result } = renderHook(() => useAiChat(makeOpts({ onElicitation })));
    const elicitation = {
      id: "q1",
      name: "ask_user",
      message: "Which board?",
      requested_schema: { type: "object" as const, properties: { answer: { type: "string" as const, enum: ["Kitchen", "Hall"] } } },
      allow_free_text: true,
    };
    act(() => {
      result.current.send("put the weather up");
    });
    await act(async () => {
      capturedHandlers?.onToolCall?.({ ...CREATE_PAGE, id: "q1", name: "ask_user", read_only: true, args: { question: "Which board?" } });
      capturedHandlers?.onElicitation?.(elicitation);
      capturedHandlers?.onDone?.({ ...DONE, reason: "awaiting_input", pending_tool_call_id: "q1" });
      resolveStream?.();
    });
    expect(result.current.status).toBe("awaiting_input");
    expect(result.current.pendingElicitation?.id).toBe("q1");
    expect(onElicitation).toHaveBeenCalledWith(elicitation);

    act(() => {
      result.current.send("Kitchen");
    });
    expect(lastBody().resume).toEqual({
      tool_call_id: "q1",
      decision: "answer",
      answer: { action: "accept", content: { answer: "Kitchen" } },
    });
    expect(result.current.messages[1].elicitation?.answer).toEqual({ action: "accept", content: { answer: "Kitchen" } });
    // The answer is not a user bubble; it rides on the resume.
    expect(result.current.messages.filter((m) => m.role === "user")).toHaveLength(1);
  });

  it("answer() with a decline resumes with the decline", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      capturedHandlers?.onElicitation?.({
        id: "q1",
        name: "ask_user",
        message: "?",
        requested_schema: { type: "object", properties: { answer: { type: "string" } } },
        allow_free_text: true,
      });
      capturedHandlers?.onDone?.({ ...DONE, reason: "awaiting_input", pending_tool_call_id: "q1" });
      resolveStream?.();
    });
    act(() => {
      result.current.answer("q1", { action: "decline" });
    });
    expect(lastBody().resume).toEqual({ tool_call_id: "q1", decision: "answer", answer: { action: "decline" } });
  });

  it("stop() marks running calls stopped and reports them", async () => {
    const onStopped = vi.fn();
    const { result } = renderHook(() => useAiChat(makeOpts({ onStopped })));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      capturedHandlers?.onToolCall?.(CREATE_PAGE);
    });
    await act(async () => {
      result.current.stop();
      resolveStream?.();
    });
    expect(result.current.messages[1].toolCalls![0].phase).toBe("stopped");
    expect(onStopped).toHaveBeenCalledWith([CREATE_PAGE]);
    expect(result.current.status).toBe("idle");
  });

  it("onError sets the error state and status", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      capturedHandlers?.onError?.("provider down");
      resolveStream?.();
    });
    expect(result.current.error).toBe("provider down");
    expect(result.current.status).toBe("error");
  });

  it("reset() clears everything", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      resolveStream?.();
    });
    act(() => {
      result.current.reset();
    });
    expect(result.current.messages).toHaveLength(0);
    expect(result.current.status).toBe("idle");
  });

  it("retryLast() re-sends from the last user message", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("first");
    });
    await act(async () => {
      capturedHandlers?.onError?.("boom");
      resolveStream?.();
    });
    act(() => {
      result.current.retryLast();
    });
    expect(result.current.messages[0]).toMatchObject({ role: "user", content: "first" });
    expect(result.current.status).toBe("streaming");
    expect(capturedBodies).toHaveLength(2);
  });
});

describe("toWireMessages", () => {
  it("renders calls with outcomes as assistant tool_calls followed by tool entries", () => {
    const history: ChatMessage[] = [
      { role: "user", content: "go" },
      {
        role: "assistant",
        content: "Creating.",
        toolCalls: [
          { ...CREATE_PAGE, phase: "ok", result: OK },
          { ...DELETE_PAGE, phase: "denied" },
          { ...CREATE_PAGE, id: "tc3", phase: "stopped" },
          { ...CREATE_PAGE, id: "tc4", phase: "running" },
        ],
      },
    ];
    expect(toWireMessages(history)).toEqual([
      { role: "user", content: "go" },
      {
        role: "assistant",
        content: "Creating.",
        tool_calls: [
          { id: "tc1", name: "create_page", args: CREATE_PAGE.args },
          { id: "tc2", name: "delete_page", args: DELETE_PAGE.args },
          { id: "tc3", name: "create_page", args: CREATE_PAGE.args },
          { id: "tc4", name: "create_page", args: CREATE_PAGE.args },
        ],
      },
      { role: "tool", tool_call_id: "tc1", name: "create_page", status: "ok", result: { page_id: "p9" } },
      { role: "tool", tool_call_id: "tc2", name: "delete_page", status: "denied", result: null },
      { role: "tool", tool_call_id: "tc3", name: "create_page", status: "interrupted", result: null },
    ]);
  });

  it("renders an error outcome as an error payload", () => {
    const history: ChatMessage[] = [
      { role: "assistant", content: "", toolCalls: [{ ...CREATE_PAGE, phase: "error", result: { ...OK, status: "error", error: "taken" } }] },
    ];
    expect(toWireMessages(history)[1]).toEqual({ role: "tool", tool_call_id: "tc1", name: "create_page", status: "error", result: { error: "taken" } });
  });
});

describe("computeAppliedSnapshot", () => {
  it("previews a create_page from its template lines", () => {
    const snap = computeAppliedSnapshot(CREATE_PAGE, undefined);
    expect(snap?.name).toBe("Morning");
    expect(snap?.line_metadata).toHaveLength(2);
  });

  it("merges an update_page over the base page", () => {
    const base = { name: "Old", template: ["A", "B"], line_metadata: [{ alignment: "center" as const, wrap: true }, { alignment: "left" as const, wrap: false }] };
    const snap = computeAppliedSnapshot({ name: "update_page", args: { page_id: "p", name: "New" } }, base);
    expect(snap).toEqual({ name: "New", template: ["A", "B"], line_metadata: base.line_metadata });
  });

  it("is undefined for tools that do not touch a page", () => {
    expect(computeAppliedSnapshot({ name: "list_pages", args: {} }, undefined)).toBeUndefined();
  });
});
