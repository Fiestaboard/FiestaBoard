import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ToolCall, ToolResult } from "@/lib/ai-chat-types";
import type { ChoreographyContext } from "@/lib/ai-choreography/types";
import { useChoreographer } from "@/lib/ai-choreography/use-choreographer";

const CALL: ToolCall = {
  id: "tc1",
  name: "update_setting",
  args: { category: "general", values: { instance_name: "Kitchen" } },
  title: "Update setting",
  read_only: false,
  destructive: false,
  requires_approval: false,
  source: "mcp",
};

const OK: ToolResult = { id: "tc1", name: "update_setting", status: "ok", summary: "ok", result: {}, error: null };

function makeCtx(): ChoreographyContext & { navigated: string[] } {
  const navigated: string[] = [];
  return {
    navigated,
    navigate: (href) => navigated.push(href),
    // The router really does move, so the stub does too: the engine skips a
    // navigate to the path it is already on, and a fixed pathname would hide
    // the second call's navigation behind the first's.
    pathname: () => navigated.at(-1)?.split("?")[0] ?? "/",
    spotlight: { show: vi.fn(), caption: vi.fn(), pulse: vi.fn(), hide: vi.fn(), ghost: vi.fn(), clearGhosts: vi.fn() },
    pageEditor: {
      isMounted: () => false,
      pageId: () => undefined,
      hasUnsavedChanges: () => false,
      begin: vi.fn(),
      setName: vi.fn(),
      setLine: vi.fn(),
      setDeviceType: vi.fn(),
      discard: vi.fn(),
      reload: async () => {},
      waitFor: async () => true,
    },
    schedule: {
      isMounted: () => false,
      openEmpty: vi.fn(),
      openEntry: vi.fn(),
      setField: vi.fn(),
      close: vi.fn(),
      waitFor: async () => true,
      waitForForm: async () => true,
    },
    t: (key) => key,
    label: (call) => call.title,
    // Instant reveals keep the sequencing observable without timers.
    reducedMotion: true,
  };
}

describe("useChoreographer", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("narrates a call, waits for its result, then settles", async () => {
    const ctx = makeCtx();
    const { result } = renderHook(() => useChoreographer(ctx));
    act(() => result.current.onToolCall(CALL));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.navigated).toEqual(["/settings?section=general"]);
    expect(ctx.spotlight.show).toHaveBeenCalled();
    expect(result.current.driving).toBe(true);
    expect(ctx.spotlight.pulse).not.toHaveBeenCalled();

    act(() => result.current.onToolResult(OK));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.spotlight.pulse).toHaveBeenCalledWith("settings.general");
    expect(ctx.spotlight.hide).toHaveBeenCalled();
    expect(result.current.driving).toBe(false);
  });

  it("plays calls strictly in order: the second waits for the first to settle", async () => {
    const ctx = makeCtx();
    const { result } = renderHook(() => useChoreographer(ctx));
    const second = { ...CALL, id: "tc2", name: "set_active_page", args: { page_id: "p1" } };
    act(() => {
      result.current.onToolCall(CALL);
      result.current.onToolCall(second);
    });
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.navigated).toEqual(["/settings?section=general"]);
    act(() => result.current.onToolResult(OK));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.navigated).toEqual(["/settings?section=general", "/"]);
  });

  it("ignores read-only calls entirely", async () => {
    const ctx = makeCtx();
    const { result } = renderHook(() => useChoreographer(ctx));
    act(() => result.current.onToolCall({ ...CALL, name: "list_pages", read_only: true }));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.spotlight.show).not.toHaveBeenCalled();
    expect(result.current.driving).toBe(false);
  });

  it("abort runs the script's stop steps and drops the queue", async () => {
    const ctx = makeCtx();
    const { result } = renderHook(() => useChoreographer(ctx));
    const create = { ...CALL, id: "tc3", name: "create_page", args: { name: "Morning", template_lines: ["A"] } };
    act(() => {
      result.current.onToolCall(create);
      result.current.onToolCall({ ...CALL, id: "tc4" });
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5);
    });
    act(() => result.current.onAbort());
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.pageEditor.discard).toHaveBeenCalled();
    expect(ctx.spotlight.hide).toHaveBeenCalled();
    expect(ctx.navigated).not.toContain("/settings?section=general");
    expect(result.current.driving).toBe(false);
  });

  it("a draft starts the walkthrough before the call exists, and the call continues it", async () => {
    const ctx = makeCtx();
    const { result } = renderHook(() => useChoreographer(ctx));
    act(() =>
      result.current.onDraft('{"op": "create_page", "args": {"name": "Morning", "template_lines": ["HELLO", "WO'),
    );
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.navigated).toEqual(["/pages", "/pages/new?device=flagship&fresh=1"]);
    expect(ctx.pageEditor.setName).toHaveBeenLastCalledWith("Morning");
    expect(ctx.pageEditor.setLine).toHaveBeenCalledWith(0, "HELLO");
    expect(ctx.pageEditor.setLine).toHaveBeenLastCalledWith(1, "WO");
    expect(result.current.driving).toBe(true);

    const create = {
      ...CALL,
      id: "tc9",
      name: "create_page",
      args: { name: "Morning", template_lines: ["HELLO", "WORLD"] },
    };
    act(() => result.current.onToolCall(create));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    // No second navigation, only the remainder is typed.
    expect(ctx.navigated).toHaveLength(2);
    expect(ctx.pageEditor.setLine).toHaveBeenLastCalledWith(1, "WORLD");

    act(() => result.current.onToolResult({ ...OK, id: "tc9", name: "create_page", result: { page_id: "p9" } }));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.pageEditor.discard).toHaveBeenCalled();
    expect(ctx.navigated).toContain("/pages/edit/p9");
    expect(result.current.driving).toBe(false);
  });

  it("a draft that never becomes a call is dropped when the turn ends, leaving nothing staged", async () => {
    const ctx = makeCtx();
    const { result } = renderHook(() => useChoreographer(ctx));
    act(() => result.current.onDraft('{"op": "create_page", "args": {"name": "Morning"'));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.pageEditor.begin).toHaveBeenCalled();
    act(() => result.current.onTurnEnd());
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.pageEditor.discard).toHaveBeenCalled();
    expect(result.current.driving).toBe(false);
  });

  it("walks a destructive call that ran without a pause", async () => {
    // Auto mode, or "don't ask again": no `awaiting_approval` frame ever
    // arrives, and the walkthrough must still show where the change landed.
    const ctx = makeCtx();
    const { result } = renderHook(() => useChoreographer(ctx));
    const del = {
      ...CALL,
      id: "tc7",
      name: "delete_page",
      args: { page_id: "p1" },
      destructive: true,
      requires_approval: true,
      auto_approved: true,
    };
    act(() => result.current.onToolCall(del));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.navigated).toEqual(["/pages"]);
    expect(ctx.spotlight.show).toHaveBeenCalledWith(expect.objectContaining({ anchor: "page.p1" }));
  });

  it("does not say a paused call is done before the user has decided", async () => {
    const ctx = makeCtx();
    const { result } = renderHook(() => useChoreographer(ctx));
    const del = {
      ...CALL,
      id: "tc8",
      name: "delete_page",
      args: { page_id: "p1" },
      destructive: true,
      requires_approval: true,
    };
    act(() => result.current.onToolCall(del));
    act(() => result.current.onAwaitingApproval(del));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.spotlight.pulse).not.toHaveBeenCalled();
    expect(ctx.spotlight.hide).not.toHaveBeenCalled();
    expect(result.current.driving).toBe(true);
  });

  it("shows Approve/Deny at the call's anchor while the server waits", async () => {
    const ctx = makeCtx();
    const { result } = renderHook(() => useChoreographer(ctx));
    const del = {
      ...CALL,
      id: "tc5",
      name: "delete_page",
      args: { page_id: "p1" },
      destructive: true,
      requires_approval: true,
    };
    act(() => result.current.onToolCall(del));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    act(() => result.current.onAwaitingApproval(del));
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.spotlight.show).toHaveBeenLastCalledWith(
      expect.objectContaining({ anchor: "page.p1", controls: "approval" }),
    );
    act(() =>
      result.current.onToolResult({ ...OK, id: "tc5", name: "delete_page", status: "denied", summary: "Not run." }),
    );
    await act(async () => {
      await vi.runAllTimersAsync();
    });
    expect(ctx.spotlight.hide).toHaveBeenCalled();
  });
});
