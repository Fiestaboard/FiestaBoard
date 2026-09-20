import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";

import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SpotlightProvider, useSpotlight } from "@/components/ai-spotlight/spotlight-provider";
import { ANCHOR_ATTR, resolveAnchor } from "@/lib/ai-choreography/anchors";

// The provider resolves its anchors through this module; spying on the real
// implementation is what lets a test count DOM queries per frame.
vi.mock("@/lib/ai-choreography/anchors", async () => {
  const actual = await vi.importActual<typeof import("@/lib/ai-choreography/anchors")>("@/lib/ai-choreography/anchors");
  return { ...actual, resolveAnchor: vi.fn(actual.resolveAnchor) };
});

const resolveAnchorMock = vi.mocked(resolveAnchor);

let api: ReturnType<typeof useSpotlight> | null = null;

function Probe() {
  api = useSpotlight();
  return null;
}

/**
 * A hand-cranked `requestAnimationFrame`: the measurement loop reschedules
 * itself, so a test that wants "ten frames" has to run them one at a time.
 */
function installFrameControl() {
  let nextId = 1;
  const pending = new Map<number, FrameRequestCallback>();
  vi.spyOn(window, "requestAnimationFrame").mockImplementation((cb: FrameRequestCallback) => {
    const id = nextId++;
    pending.set(id, cb);
    return id;
  });
  vi.spyOn(window, "cancelAnimationFrame").mockImplementation((id: number) => {
    pending.delete(id);
  });
  return function runFrames(count = 1) {
    for (let i = 0; i < count; i++) {
      const due = [...pending.entries()];
      pending.clear();
      act(() => {
        for (const [, cb] of due) cb(performance.now());
      });
    }
  };
}

function makeAnchor(id: string, tag = "input") {
  const el = document.createElement(tag);
  el.setAttribute(ANCHOR_ATTR, id);
  document.body.appendChild(el);
  return el;
}

const RING_ANCHOR = "settings.general.instance_name";
const GHOST_ANCHORS = [
  "settings.location.latitude",
  "settings.location.longitude",
  "settings.polling.interval_seconds",
];

describe("spotlight measurement loop", () => {
  let runFrames: (count?: number) => void;

  beforeEach(() => {
    api = null;
    resolveAnchorMock.mockClear();
    runFrames = installFrameControl();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    for (const el of document.querySelectorAll(`[${ANCHOR_ATTR}]`)) el.remove();
  });

  it("resolves each anchor once, not once per frame", () => {
    makeAnchor(RING_ANCHOR);
    for (const id of GHOST_ANCHORS) makeAnchor(id);
    render(
      <SpotlightProvider>
        <Probe />
      </SpotlightProvider>,
    );
    act(() => {
      api!.show({ anchor: RING_ANCHOR, caption: "Working" });
      for (const id of GHOST_ANCHORS) api!.ghost(id, "Kitchen Board", 0.5, "auto");
    });

    runFrames(1);
    resolveAnchorMock.mockClear();
    runFrames(20);

    // Twenty frames over four anchors is eighty DOM queries the old loop made
    // and the cache makes none of: the elements never left the document.
    expect(resolveAnchorMock).not.toHaveBeenCalled();
  });

  it("re-resolves an anchor whose element was replaced", () => {
    const anchor = makeAnchor(RING_ANCHOR);
    render(
      <SpotlightProvider>
        <Probe />
      </SpotlightProvider>,
    );
    act(() => api!.show({ anchor: RING_ANCHOR, caption: "Working" }));
    runFrames(2);

    // The route re-renders and hands the same anchor id to a new element.
    anchor.remove();
    const replacement = makeAnchor(RING_ANCHOR);
    const rects = vi.spyOn(replacement, "getBoundingClientRect");
    resolveAnchorMock.mockClear();
    runFrames(1);

    expect(resolveAnchorMock).toHaveBeenCalledWith(RING_ANCHOR);
    expect(rects).toHaveBeenCalled();
  });

  it("takes every measurement before it writes any style", () => {
    makeAnchor(RING_ANCHOR);
    for (const id of GHOST_ANCHORS) makeAnchor(id);
    render(
      <SpotlightProvider>
        <Probe />
      </SpotlightProvider>,
    );
    act(() => {
      api!.show({ anchor: RING_ANCHOR, caption: "Working" });
      for (const id of GHOST_ANCHORS) api!.ghost(id, "Kitchen Board", 0.5, "auto");
    });

    // Every measurement and every style write, in the order they happen.
    const order: string[] = [];
    let offset = 0;
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function measured() {
      order.push("read");
      return {
        x: offset,
        y: offset,
        left: offset,
        top: offset,
        right: offset + 120,
        bottom: offset + 32,
        width: 120,
        height: 32,
        toJSON: () => ({}),
      } as DOMRect;
    });
    // Take the prototype off a real element: jsdom's `window.CSSStyleDeclaration`
    // is not necessarily the object `element.style` inherits from.
    const styleProto = Object.getPrototypeOf(document.createElement("div").style);
    const restore: Array<[string, PropertyDescriptor]> = [];
    for (const prop of ["transform", "width", "height", "font", "lineHeight", "opacity"]) {
      const descriptor = Object.getOwnPropertyDescriptor(styleProto, prop);
      if (!descriptor?.set) throw new Error(`style.${prop} has no setter to observe`);
      restore.push([prop, descriptor]);
      Object.defineProperty(styleProto, prop, {
        ...descriptor,
        set(this: CSSStyleDeclaration, value: string) {
          order.push("write");
          descriptor.set!.call(this, value);
        },
      });
    }

    try {
      // A warm-up frame first: the assertion is about a steady-state frame,
      // not about whatever the first commit happens to write.
      runFrames(1);
      order.length = 0;
      // Everything has moved, so this frame really does write.
      offset = 40;
      runFrames(1);
    } finally {
      for (const [prop, descriptor] of restore) Object.defineProperty(styleProto, prop, descriptor);
    }

    const firstWrite = order.indexOf("write");
    const lastRead = order.lastIndexOf("read");
    expect(order.filter((o) => o === "read").length).toBeGreaterThan(1);
    expect(firstWrite).toBeGreaterThan(-1);
    // Read, write, read, write is what forces one synchronous reflow per
    // ghost. Every read has to come first for the frame to cost one layout.
    expect(lastRead).toBeLessThan(firstWrite);
  });

  it("reads the replica's computed font once, not once per frame", () => {
    makeAnchor(RING_ANCHOR, "textarea");
    render(
      <SpotlightProvider>
        <Probe />
      </SpotlightProvider>,
    );
    act(() => api!.ghost(RING_ANCHOR, "Kitchen Board", 0.5, "replica"));

    runFrames(1);
    const computed = vi.spyOn(window, "getComputedStyle");
    runFrames(20);

    expect(computed).not.toHaveBeenCalled();
  });
});

describe("spotlight z-layer", () => {
  const require = createRequire(import.meta.url);

  function tokens(css: string) {
    const found: Record<string, number> = {};
    for (const [, name, value] of css.matchAll(/(--z-[a-z-]+):\s*(\d+)\s*;/g)) found[name] = Number(value);
    return found;
  }

  it("sits above every layer of chrome it can be asked to highlight", () => {
    const ladder = tokens(fs.readFileSync(require.resolve("@fiestaboard/ui/theme.css"), "utf8"));
    // Vitest runs from `web/`, where the app stylesheet lives.
    const app = tokens(fs.readFileSync(path.join(process.cwd(), "app/globals.css"), "utf8"));
    const spotlight = app["--z-spotlight"];

    expect(spotlight, "web/app/globals.css must define --z-spotlight").toBeTypeOf("number");
    // Anything on this list can host a control the walkthrough highlights,
    // and a ring drawn under it is the bug in #2040.
    for (const layer of [
      "--z-sidebar",
      "--z-sidebar-toggle",
      "--z-mobile-backdrop",
      "--z-mobile-menu",
      "--z-mobile-header",
      "--z-sheet",
      "--z-select",
      "--z-modal",
      "--z-popover",
    ]) {
      expect(ladder[layer], `${layer} missing from @fiestaboard/ui/theme.css`).toBeTypeOf("number");
      expect(spotlight, `--z-spotlight must beat ${layer}`).toBeGreaterThan(ladder[layer]);
    }
    // The tooltip stays on top: it is the thing that explains the control the
    // ring is drawn around.
    expect(spotlight).toBeLessThan(ladder["--z-tooltip"]);
  });

  it("layers the overlay with the token rather than a hardcoded number", () => {
    const anchor = makeAnchor(RING_ANCHOR);
    render(
      <SpotlightProvider>
        <Probe />
      </SpotlightProvider>,
    );
    act(() => api!.show({ anchor: RING_ANCHOR, caption: "Working" }));
    const overlay = document.querySelector("[data-ai-spotlight]");
    expect(overlay).not.toBeNull();
    expect(overlay!.className).toContain("z-[var(--z-spotlight)]");
    anchor.remove();
  });
});
