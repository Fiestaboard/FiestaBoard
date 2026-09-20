import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ANCHOR_ATTR } from "@/lib/ai-choreography/anchors";
import {
  ChoreographyAborted,
  FAST_FACTOR,
  MAX_FIELD_MS,
  MS_PER_CHAR,
  revealDuration,
  runSteps,
} from "@/lib/ai-choreography/engine";
import type { ChoreographyContext, SpotlightApi, Step } from "@/lib/ai-choreography/types";

function makeCtx(overrides: Partial<ChoreographyContext> = {}): {
  ctx: ChoreographyContext;
  spotlight: { [K in keyof SpotlightApi]: ReturnType<typeof vi.fn> };
  editor: Record<string, ReturnType<typeof vi.fn>>;
  navigated: string[];
} {
  const spotlight = {
    show: vi.fn(),
    caption: vi.fn(),
    pulse: vi.fn(),
    hide: vi.fn(),
    ghost: vi.fn(),
    clearGhosts: vi.fn(),
  };
  const editor = {
    isMounted: vi.fn(() => true),
    pageId: vi.fn(() => undefined),
    hasUnsavedChanges: vi.fn(() => false),
    begin: vi.fn(),
    setName: vi.fn(),
    setLine: vi.fn(),
    setDeviceType: vi.fn(),
    discard: vi.fn(),
    reload: vi.fn(async () => {}),
    waitFor: vi.fn(async () => true),
  };
  const navigated: string[] = [];
  const ctx: ChoreographyContext = {
    navigate: (href) => navigated.push(href),
    pathname: () => "/",
    spotlight,
    pageEditor: editor as unknown as ChoreographyContext["pageEditor"],
    schedule: {
      isMounted: () => true,
      openEmpty: vi.fn(),
      openEntry: vi.fn(),
      setField: vi.fn(),
      close: vi.fn(),
      waitFor: async () => true,
      waitForForm: async () => true,
    },
    t: (key, params) => (params ? `${key}:${JSON.stringify(params)}` : key),
    label: (call) => call.name,
    reducedMotion: false,
    ...overrides,
  };
  return { ctx, spotlight, editor, navigated };
}

describe("runSteps", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("types a value in chunks, ending on the full value", async () => {
    const { ctx, editor } = makeCtx();
    const steps: Step[] = [{ kind: "type", target: { bridge: "page-editor", field: "name" }, value: "Morning" }];
    const run = runSteps(steps, ctx, { signal: new AbortController().signal, isFast: () => false });
    await vi.runAllTimersAsync();
    await run;
    const values = editor.setName.mock.calls.map((c) => c[0]);
    expect(values[values.length - 1]).toBe("Morning");
    expect(values.length).toBeGreaterThan(1);
    // Every intermediate value is a prefix of the final one.
    for (const v of values) expect("Morning".startsWith(v)).toBe(true);
  });

  it("reveals instantly under reduced motion", async () => {
    const { ctx, editor } = makeCtx({ reducedMotion: true });
    await runSteps(
      [{ kind: "type", target: { bridge: "page-editor", field: "line", index: 2 }, value: "HELLO WORLD" }],
      ctx,
      {
        signal: new AbortController().signal,
        isFast: () => false,
      },
    );
    expect(editor.setLine).toHaveBeenCalledTimes(1);
    expect(editor.setLine).toHaveBeenCalledWith(2, "HELLO WORLD");
  });

  it("stops between chunks when aborted and throws ChoreographyAborted", async () => {
    const { ctx, editor } = makeCtx();
    const controller = new AbortController();
    const run = runSteps(
      [{ kind: "type", target: { bridge: "page-editor", field: "name" }, value: "A long page name here" }],
      ctx,
      { signal: controller.signal, isFast: () => false },
    );
    const failing = run.catch((e) => e);
    await vi.advanceTimersByTimeAsync(40);
    controller.abort();
    await vi.runAllTimersAsync();
    await expect(failing).resolves.toBeInstanceOf(ChoreographyAborted);
    const last = editor.setName.mock.calls.at(-1)?.[0] as string;
    expect(last.length).toBeLessThan("A long page name here".length);
  });

  it("runs faster once the result is in", () => {
    const { ctx } = makeCtx();
    const slow = revealDuration("x".repeat(100), ctx, false);
    const fast = revealDuration("x".repeat(100), ctx, true);
    expect(slow).toBe(MAX_FIELD_MS);
    expect(fast).toBe(MAX_FIELD_MS / FAST_FACTOR);
    expect(revealDuration("abc", ctx, false)).toBe(3 * MS_PER_CHAR);
  });

  it("waits for an anchor to appear, then spotlights it", async () => {
    const { ctx, spotlight } = makeCtx();
    const run = runSteps(
      [
        { kind: "waitFor", anchor: "pages.new", timeoutMs: 1000 },
        { kind: "spotlight", anchor: "pages.new", caption: "Opening" },
      ],
      ctx,
      { signal: new AbortController().signal, isFast: () => false },
    );
    await vi.advanceTimersByTimeAsync(120);
    expect(spotlight.show).not.toHaveBeenCalled();
    const el = document.createElement("button");
    el.setAttribute(ANCHOR_ATTR, "pages.new");
    document.body.appendChild(el);
    await vi.runAllTimersAsync();
    await run;
    expect(spotlight.show).toHaveBeenCalledWith({
      anchor: "pages.new",
      caption: "Opening",
      tone: undefined,
      controls: undefined,
    });
  });

  it("navigates only when the path changes, and always for a query", async () => {
    const { ctx, navigated } = makeCtx({ pathname: () => "/pages" });
    // Every navigate lets the router commit on a timer, so the promise is
    // held until the fake clock runs — awaiting it first would deadlock.
    const run = runSteps(
      [
        { kind: "navigate", href: "/pages" },
        { kind: "navigate", href: "/pages/new?fresh=1" },
        { kind: "navigate", href: "/schedule" },
      ],
      ctx,
      { signal: new AbortController().signal, isFast: () => true },
    );
    await vi.runAllTimersAsync();
    await run;
    expect(navigated).toEqual(["/pages/new?fresh=1", "/schedule"]);
  });

  it("ghosts a value progressively and badges instantly", async () => {
    const { ctx, spotlight } = makeCtx();
    const run = runSteps(
      [
        { kind: "ghost", anchor: "settings.general.instance_name", value: "Kitchen", variant: "replica" },
        { kind: "ghost", anchor: "settings.display.reduce_motion", value: "On", variant: "badge" },
      ],
      ctx,
      { signal: new AbortController().signal, isFast: () => false },
    );
    await vi.runAllTimersAsync();
    await run;
    const replica = spotlight.ghost.mock.calls.filter((c) => c[0] === "settings.general.instance_name");
    expect(replica.length).toBeGreaterThan(1);
    expect(replica.at(-1)?.[2]).toBe(1);
    const badge = spotlight.ghost.mock.calls.filter((c) => c[0] === "settings.display.reduce_motion");
    expect(badge).toEqual([["settings.display.reduce_motion", "On", 1, "badge"]]);
  });
});
