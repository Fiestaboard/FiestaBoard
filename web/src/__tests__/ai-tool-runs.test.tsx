import { describe, expect, it } from "vitest";

import { groupToolCalls } from "@/components/ai-tool-runs";
import type { ToolCallDisplay } from "@/lib/ai-chat-types";

// Five schedule creations in a row are five cards, each up to two lines, and
// they push the conversation off the screen. A run of the same successful
// action collapses to one row — but only ever a run of the same successful
// action: anything the user refused, anything that failed, and anything that
// needed their approval stays visible as itself.

function call(name: string, over: Partial<ToolCallDisplay> = {}): ToolCallDisplay {
  return {
    id: over.id ?? `${name}-${Math.random().toString(36).slice(2, 8)}`,
    name,
    args: {},
    title: name,
    read_only: false,
    destructive: false,
    requires_approval: false,
    source: "mcp",
    phase: "ok",
    ...over,
  } as ToolCallDisplay;
}

describe("groupToolCalls", () => {
  it("collapses a run of the same successful action, counting every one of them", () => {
    const calls = [call("create_schedule"), call("create_schedule"), call("create_schedule"), call("create_schedule")];
    const groups = groupToolCalls(calls);
    expect(groups).toHaveLength(1);
    expect(groups[0]).toMatchObject({ kind: "run", name: "create_schedule" });
    expect(groups[0].kind === "run" && groups[0].calls).toHaveLength(4);
  });

  it("leaves a single call exactly as it was", () => {
    const only = call("create_schedule");
    expect(groupToolCalls([only])).toEqual([{ kind: "single", call: only }]);
  });

  it("does not collapse two calls of different tools", () => {
    const groups = groupToolCalls([call("create_schedule"), call("set_schedule_mode")]);
    expect(groups.map((g) => g.kind)).toEqual(["single", "single"]);
  });

  it("starts a new run when the tool changes and back again", () => {
    const groups = groupToolCalls([
      call("create_schedule"),
      call("create_schedule"),
      call("set_schedule_mode"),
      call("create_page"),
      call("create_page"),
    ]);
    expect(groups.map((g) => g.kind)).toEqual(["run", "single", "run"]);
  });

  it("breaks a run around a call that failed, and leaves the failure its own card", () => {
    const groups = groupToolCalls([
      call("create_schedule"),
      call("create_schedule"),
      call("create_schedule", { phase: "error" }),
      call("create_schedule"),
      call("create_schedule"),
    ]);
    expect(groups.map((g) => g.kind)).toEqual(["run", "single", "run"]);
    expect(groups[1]).toMatchObject({ kind: "single" });
    expect(groups[1].kind === "single" && groups[1].call.phase).toBe("error");
  });

  it("never hides a call the user denied", () => {
    const groups = groupToolCalls([
      call("delete_page", { phase: "ok" }),
      call("delete_page", { phase: "denied" }),
      call("delete_page", { phase: "ok" }),
    ]);
    expect(groups.every((g) => g.kind === "single")).toBe(true);
  });

  it("never hides a call that was gated on the user's approval, even a successful one", () => {
    const groups = groupToolCalls([
      call("delete_schedule", { requires_approval: true }),
      call("delete_schedule", { requires_approval: true }),
    ]);
    expect(groups.map((g) => g.kind)).toEqual(["single", "single"]);
  });

  it("does not collapse calls that are still running", () => {
    const groups = groupToolCalls([
      call("create_schedule", { phase: "running" }),
      call("create_schedule", { phase: "running" }),
    ]);
    expect(groups.map((g) => g.kind)).toEqual(["single", "single"]);
  });

  it("keeps a stopped call visible on its own", () => {
    const groups = groupToolCalls([call("create_page"), call("create_page", { phase: "stopped" })]);
    expect(groups.map((g) => g.kind)).toEqual(["single", "single"]);
  });

  it("keeps the calls in the order they happened", () => {
    const first = call("create_schedule", { id: "a" });
    const second = call("create_schedule", { id: "b" });
    const groups = groupToolCalls([first, second]);
    expect(groups[0].kind === "run" && groups[0].calls.map((c) => c.id)).toEqual(["a", "b"]);
  });
});
