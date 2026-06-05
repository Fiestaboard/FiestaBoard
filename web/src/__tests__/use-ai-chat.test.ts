import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ToolCall } from "@/lib/ai-chat-types";
import type * as apiStreamModule from "@/lib/api-stream";
import { useAiChat } from "@/lib/use-ai-chat";

// Control streamChat from tests via a captured reference.
let capturedHandlers: Parameters<(typeof apiStreamModule)["streamChat"]>[1] | null = null;
let resolveStream: (() => void) | null = null;

vi.mock("@/lib/api-stream", () => ({
  streamChat: vi.fn(
    (_body: unknown, handlers: unknown, _signal?: unknown) =>
      new Promise<void>((resolve) => {
        capturedHandlers = handlers as any;
        resolveStream = resolve;
      }),
  ),
}));

function makeOpts(overrides: Partial<Parameters<typeof useAiChat>[0]> = {}) {
  return {
    getTurnContext: () => ({ deviceType: "flagship" as const, surface: "global" as const }),
    onToolCall: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  capturedHandlers = null;
  resolveStream = null;
  vi.clearAllMocks();
});

describe("useAiChat", () => {
  it("starts with idle status, empty messages, and no error", () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    expect(result.current.status).toBe("idle");
    expect(result.current.messages).toHaveLength(0);
    expect(result.current.error).toBeNull();
  });

  it("send() adds the user message immediately", () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hello");
    });
    expect(result.current.messages[0]).toMatchObject({ role: "user", content: "hello" });
  });

  it("send() trims whitespace and ignores blank input", () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("   ");
    });
    expect(result.current.messages).toHaveLength(0);
  });

  it("send() sets status to streaming", () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    expect(result.current.status).toBe("streaming");
  });

  it("send() appends a pending assistant placeholder", () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    const last = result.current.messages[result.current.messages.length - 1];
    expect(last.role).toBe("assistant");
    expect(last.pending).toBe(true);
  });

  it("onText handler appends delta to the in-flight assistant message", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      capturedHandlers?.onText?.("hello ");
    });
    await act(async () => {
      capturedHandlers?.onText?.("world");
    });
    const last = result.current.messages[result.current.messages.length - 1];
    expect(last.content).toBe("hello world");
  });

  it("onToolCall attaches tool call to the assistant message and fires callback", async () => {
    const onToolCall = vi.fn();
    const { result } = renderHook(() => useAiChat(makeOpts({ onToolCall })));
    act(() => {
      result.current.send("hi");
    });
    const call: ToolCall = {
      id: "tc1",
      op: "replace_page",
      args: { name: "p", template: [], line_metadata: [], duration_seconds: 300 },
    };
    await act(async () => {
      capturedHandlers?.onToolCall?.(call);
    });
    const last = result.current.messages[result.current.messages.length - 1];
    expect(last.toolCalls).toHaveLength(1);
    expect(last.toolCalls![0].op).toBe("replace_page");
    expect(onToolCall).toHaveBeenCalledWith(call);
  });

  it("onWarning attaches warning to the assistant message", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      capturedHandlers?.onWarning?.("rate limited");
    });
    const last = result.current.messages[result.current.messages.length - 1];
    expect(last.warnings).toContain("rate limited");
  });

  it("onError sets the error state", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      capturedHandlers?.onError?.("oops");
    });
    expect(result.current.error).toBe("oops");
  });

  it("status returns to idle after the stream completes", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      resolveStream?.();
    });
    expect(result.current.status).toBe("idle");
  });

  it("status is 'error' after stream with an error", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      capturedHandlers?.onError?.("fail");
    });
    await act(async () => {
      resolveStream?.();
    });
    expect(result.current.status).toBe("error");
  });

  it("pending flag is cleared when stream ends", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      resolveStream?.();
    });
    const last = result.current.messages[result.current.messages.length - 1];
    expect(last.pending).toBe(false);
  });

  it("cancel() aborts the in-flight stream", () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    expect(() =>
      act(() => {
        result.current.cancel();
      }),
    ).not.toThrow();
  });

  it("reset() clears messages, status, and error", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      capturedHandlers?.onError?.("bad");
      resolveStream?.();
    });
    act(() => {
      result.current.reset();
    });
    expect(result.current.messages).toHaveLength(0);
    expect(result.current.status).toBe("idle");
    expect(result.current.error).toBeNull();
  });

  it("retryLast() re-sends from the last user message", async () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("hi");
    });
    await act(async () => {
      resolveStream?.();
    });
    // After first stream ends, there is a user + assistant message
    act(() => {
      result.current.retryLast();
    });
    expect(result.current.status).toBe("streaming");
  });

  it("retryLast() is a no-op when there are no user messages", () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.retryLast();
    });
    expect(result.current.status).toBe("idle");
  });

  it("apply_patch tool call computes appliedSnapshot from base snapshot", async () => {
    const onToolCall = vi.fn();
    const baseSnapshot = {
      name: "My Page",
      template: ["hello", "world"],
      line_metadata: [
        { alignment: "left" as const, wrap: false },
        { alignment: "left" as const, wrap: false },
      ],
    };
    const { result } = renderHook(() =>
      useAiChat(
        makeOpts({
          onToolCall,
          getTurnContext: () => ({
            deviceType: "flagship" as const,
            surface: "editor" as const,
            currentPage: baseSnapshot,
          }),
        }),
      ),
    );
    act(() => {
      result.current.send("patch it");
    });
    const call: ToolCall = {
      id: "tc2",
      op: "apply_patch",
      args: {
        changes: [{ type: "replace_line", index: 0, text: "hi" }],
      },
    };
    await act(async () => {
      capturedHandlers?.onToolCall?.(call);
    });
    const last = result.current.messages[result.current.messages.length - 1];
    expect(last.toolCalls).toHaveLength(1);
    expect(last.toolCalls![0].appliedSnapshot?.template[0]).toBe("hi");
    expect(last.toolCalls![0].appliedSnapshot?.name).toBe("My Page");
  });

  it("apply_patch with rename updates the snapshot name", async () => {
    const onToolCall = vi.fn();
    const baseSnapshot = {
      name: "Old Name",
      template: ["line1"],
      line_metadata: [{ alignment: "left" as const, wrap: false }],
    };
    const { result } = renderHook(() =>
      useAiChat(
        makeOpts({
          onToolCall,
          getTurnContext: () => ({
            deviceType: "flagship" as const,
            surface: "editor" as const,
            currentPage: baseSnapshot,
          }),
        }),
      ),
    );
    act(() => {
      result.current.send("rename it");
    });
    const call: ToolCall = {
      id: "tc3",
      op: "apply_patch",
      args: {
        rename: "New Name",
        changes: [],
      },
    };
    await act(async () => {
      capturedHandlers?.onToolCall?.(call);
    });
    const last = result.current.messages[result.current.messages.length - 1];
    expect(last.toolCalls![0].appliedSnapshot?.name).toBe("New Name");
  });

  it("resume() injects a tool-result message with isToolResult=true and starts streaming", () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.send("install weather");
    });
    // Stream ends
    act(() => {
      resolveStream?.();
    });
    // Now chain via resume
    act(() => {
      result.current.resume('[Tool result: install_plugin for "openweather" → Success.]');
    });
    const msgs = result.current.messages;
    const resultMsg = msgs.find((m) => m.isToolResult);
    expect(resultMsg).toBeDefined();
    expect(resultMsg?.role).toBe("user");
    expect(resultMsg?.isToolResult).toBe(true);
    expect(resultMsg?.content).toContain("Tool result");
    // Should be streaming again
    expect(result.current.status).toBe("streaming");
  });

  it("resume() without prior send also starts a stream", () => {
    const { result } = renderHook(() => useAiChat(makeOpts()));
    act(() => {
      result.current.resume('[Tool result: enable_plugin for "stocks" → Success.]');
    });
    expect(result.current.status).toBe("streaming");
    const resultMsg = result.current.messages.find((m) => m.isToolResult);
    expect(resultMsg?.isToolResult).toBe(true);
  });

  it("apply_patch without a base snapshot yields no appliedSnapshot", async () => {
    const onToolCall = vi.fn();
    const { result } = renderHook(() =>
      useAiChat(
        makeOpts({
          onToolCall,
          getTurnContext: () => ({ deviceType: "flagship" as const, surface: "global" as const }),
        }),
      ),
    );
    act(() => {
      result.current.send("patch");
    });
    const call: ToolCall = {
      id: "tc4",
      op: "apply_patch",
      args: { changes: [{ type: "replace_line", index: 0, text: "x" }] },
    };
    await act(async () => {
      capturedHandlers?.onToolCall?.(call);
    });
    const last = result.current.messages[result.current.messages.length - 1];
    expect(last.toolCalls![0].appliedSnapshot).toBeUndefined();
  });
});
