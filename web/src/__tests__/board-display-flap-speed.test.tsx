/**
 * Behavioural guard for the on-screen split-flap cascade and the flap-speed
 * setting that paces it.
 *
 * These tests drive a real message change through the real `BoardDisplay` and
 * measure what a user would see. That framing is the point: before this change
 * the board *snapped* on a message change — the loading-lifecycle effect also
 * depended on `targetCharIndex` and its idle branch set the character index to
 * the new target, so the transition effect's updater saw `current === target`
 * and cancelled the cascade it had just started, in the same batch. Same root
 * cause as FiestaUI issue #196, same fix as its PR #202.
 *
 * The existing `board-display-transition.test.tsx` only ever exercises the
 * loading -> loaded path, which was never broken, so it stayed green
 * throughout. A snapshot or a source-reading assertion would not have caught
 * this either: the bug is purely behavioural.
 */
import { FLAP_SPEED_PRESETS } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BoardDisplay } from "@/components/board-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { mockDisplaySettings } from "./mocks/handlers";
import { server } from "./mocks/server";

const API_BASE = "/api";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

/** Point `/settings/all` at a specific display block for one test. */
function withDisplaySettings(overrides: Partial<typeof mockDisplaySettings>) {
  server.use(
    http.get(`${API_BASE}/settings/all`, () =>
      HttpResponse.json({ display: { ...mockDisplaySettings, ...overrides } }),
    ),
  );
}

/** Make `matchMedia` report a specific answer for one query. */
function setMediaQuery(query: string, matches: boolean) {
  const original = window.matchMedia;
  window.matchMedia = ((q: string) => {
    const result = original(q) as MediaQueryList;
    return q === query ? { ...result, matches, media: q } : result;
  }) as typeof window.matchMedia;
  return () => {
    window.matchMedia = original;
  };
}

interface CascadeReading {
  /** Distinct `data-current-char` values seen on tile (0,0), in order. */
  chars: string[];
  /** Whether any tile ever committed a render with `data-is-transitioning`. */
  sawTransitioning: boolean;
  /** Peak number of mounted flap layers across the whole board. */
  peakFlapLayers: number;
  /** Milliseconds until tile (0,0) first shows its target, or null. */
  settleMs: number | null;
}

/**
 * Drive a message change and sample the board every `sampleMs` until it has
 * settled (or the budget runs out).
 */
async function measureCascade(
  container: HTMLElement,
  rerender: (ui: React.ReactElement) => void,
  next: React.ReactElement,
  { sampleMs = 4, budgetMs = 30000 }: { sampleMs?: number; budgetMs?: number } = {},
): Promise<CascadeReading> {
  const tile = () => container.querySelector('[data-testid="char-tile-0-0"]');
  const target = tile()?.getAttribute("data-target-char") ?? null;

  // Seed with the character on screen before the message changed, so the
  // sequence below reads as the full walk rather than starting one step in.
  const chars: string[] = [];
  const before = tile()?.getAttribute("data-current-char");
  if (before != null) chars.push(before);

  rerender(next);

  let sawTransitioning = false;
  let peakFlapLayers = 0;
  let settleMs: number | null = null;

  const steps = Math.ceil(budgetMs / sampleMs);
  for (let i = 0; i < steps; i++) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(sampleMs);
    });
    const el = tile();
    if (!el) continue;

    const char = el.getAttribute("data-current-char");
    if (char !== null && chars[chars.length - 1] !== char) chars.push(char);
    if (el.getAttribute("data-is-transitioning") === "true") sawTransitioning = true;

    // The flap layers only exist while a tile is mid-flip; counting them is
    // the DOM-level proof that the animation actually mounted rather than the
    // character merely changing.
    const layers = container.querySelectorAll('[style*="flapDown"], [style*="flapUp"]').length;
    if (layers > peakFlapLayers) peakFlapLayers = layers;

    const newTarget = el.getAttribute("data-target-char");
    if (settleMs === null && newTarget !== null && char === newTarget && newTarget !== target) {
      settleMs = (i + 1) * sampleMs;
      // Keep sampling a couple more frames so `isTransitioning` can clear.
      if (i + 2 < steps) continue;
    }
    if (settleMs !== null && el.getAttribute("data-is-transitioning") === "false") break;
  }

  return { chars, sawTransitioning, peakFlapLayers, settleMs };
}

describe("BoardDisplay message-change cascade", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("steps through intermediate characters and mounts flap layers", async () => {
    const { container, rerender } = render(<BoardDisplay message="A" isLoading={false} size="md" />, {
      wrapper: TestWrapper,
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });

    // "A" is index 1 and "F" is index 6 on the character drum, so a correct
    // cascade walks B, C, D, E, F — five steps, no shortcuts.
    const reading = await measureCascade(container, rerender, <BoardDisplay message="F" isLoading={false} size="md" />);

    expect(reading.chars).toEqual(["A", "B", "C", "D", "E", "F"]);
    expect(reading.sawTransitioning).toBe(true);
    expect(reading.peakFlapLayers).toBeGreaterThan(0);
  });

  it("settles in a time that scales with the chosen flap speed", async () => {
    // "A" (1) -> "K" (11) is ten steps: the first flips immediately and the
    // remaining nine are one interval apart, so settle ~= 9 * stepMs.
    const presets = ["hardware", "quick", "standard", "relaxed"] as const;
    const settled: Record<string, number> = {};

    for (const preset of presets) {
      const { container, rerender, unmount } = render(
        <BoardDisplay message="A" isLoading={false} size="md" flapSpeed={preset} />,
        { wrapper: TestWrapper },
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(200);
      });

      const reading = await measureCascade(
        container,
        rerender,
        <BoardDisplay message="K" isLoading={false} size="md" flapSpeed={preset} />,
        { sampleMs: 2 },
      );

      expect(reading.chars, `flapSpeed="${preset}" did not cascade`).toEqual([
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "I",
        "J",
        "K",
      ]);
      expect(reading.settleMs, `flapSpeed="${preset}" never settled`).not.toBeNull();
      settled[preset] = reading.settleMs as number;
      unmount();
    }

    // Strictly ordered: a faster preset must settle sooner than a slower one.
    expect(settled.hardware).toBeLessThan(settled.quick);
    expect(settled.quick).toBeLessThan(settled.standard);
    expect(settled.standard).toBeLessThan(settled.relaxed);

    // And close to the arithmetic, not merely ordered — the sampling interval
    // plus one step is the whole tolerance.
    for (const preset of presets) {
      const stepMs = FLAP_SPEED_PRESETS[preset];
      const expected = 9 * stepMs;
      expect(
        Math.abs(settled[preset] - expected),
        `flapSpeed="${preset}" settled in ${settled[preset]}ms, expected ~${expected}ms`,
      ).toBeLessThanOrEqual(stepMs + 4);
    }
  }, 60000);

  it("honours the { durationMs } escape hatch, clamped to the supported range", async () => {
    // 4ms is below the 8ms floor, so it must behave as 8ms: nine steps = 72ms.
    const { container, rerender } = render(
      <BoardDisplay message="A" isLoading={false} size="md" flapSpeed={{ durationMs: 4 }} />,
      { wrapper: TestWrapper },
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });

    const reading = await measureCascade(
      container,
      rerender,
      <BoardDisplay message="K" isLoading={false} size="md" flapSpeed={{ durationMs: 4 }} />,
      { sampleMs: 1 },
    );

    expect(reading.settleMs).not.toBeNull();
    expect(Math.abs((reading.settleMs as number) - 72)).toBeLessThanOrEqual(9);
  });

  it("retargets in place when a second message lands mid-cascade", async () => {
    // The other half of FiestaUI PR #202: with the stepper owned by an
    // effect's cleanup, a second message mid-cascade tore down the interval
    // and left the tile stuck with isTransitioning true forever.
    const { container, rerender } = render(<BoardDisplay message="A" isLoading={false} size="md" />, {
      wrapper: TestWrapper,
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });

    const tile = () => container.querySelector('[data-testid="char-tile-0-0"]');

    rerender(<BoardDisplay message="Z" isLoading={false} size="md" />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(240); // mid-cascade, ~D
    });
    expect(tile()?.getAttribute("data-is-transitioning")).toBe("true");

    rerender(<BoardDisplay message="M" isLoading={false} size="md" />);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });

    expect(tile()?.getAttribute("data-current-char")).toBe("M");
    expect(tile()?.getAttribute("data-is-transitioning")).toBe("false");
  });

  it("snaps with no flap layers when the board-animations kill switch is off", async () => {
    withDisplaySettings({ board_animations: "off" });

    const { container, rerender } = render(<BoardDisplay message="A" isLoading={false} size="md" />, {
      wrapper: TestWrapper,
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(200);
    });

    const reading = await measureCascade(
      container,
      rerender,
      <BoardDisplay message="F" isLoading={false} size="md" />,
      { budgetMs: 2000 },
    );

    expect(reading.chars).toEqual(["A", "F"]);
    expect(reading.peakFlapLayers).toBe(0);
  });

  it("snaps with no flap layers under prefers-reduced-motion, whatever the speed", async () => {
    // A relaxed cascade is the worst possible outcome for a user who asked for
    // reduced motion: ~70 consecutive flips at 130ms each. The setting must
    // not be able to buy its way past the preference. FiestaUI issue #180.
    const restore = setMediaQuery("(prefers-reduced-motion: reduce)", true);
    try {
      const { container, rerender } = render(
        <BoardDisplay message="A" isLoading={false} size="md" flapSpeed="relaxed" />,
        { wrapper: TestWrapper },
      );
      await act(async () => {
        await vi.advanceTimersByTimeAsync(200);
      });

      const reading = await measureCascade(
        container,
        rerender,
        <BoardDisplay message="F" isLoading={false} size="md" flapSpeed="relaxed" />,
        { budgetMs: 3000 },
      );

      expect(reading.chars).toEqual(["A", "F"]);
      expect(reading.sawTransitioning).toBe(false);
      expect(reading.peakFlapLayers).toBe(0);
    } finally {
      restore();
    }
  });

  it("takes the cadence from the stored setting when no flapSpeed prop is given", async () => {
    withDisplaySettings({ board_flap_speed: "relaxed" });

    const { container, rerender } = render(<BoardDisplay message="A" isLoading={false} size="md" />, {
      wrapper: TestWrapper,
    });
    // The query has to resolve before the board can read the setting.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    const reading = await measureCascade(
      container,
      rerender,
      <BoardDisplay message="K" isLoading={false} size="md" />,
      { sampleMs: 5 },
    );

    // 9 steps at the relaxed 130ms = 1170ms; at the 80ms default it would be
    // 720ms, so this cannot pass by accident on the old constant.
    expect(reading.settleMs).not.toBeNull();
    expect(Math.abs((reading.settleMs as number) - 9 * FLAP_SPEED_PRESETS.relaxed)).toBeLessThanOrEqual(
      FLAP_SPEED_PRESETS.relaxed,
    );
  }, 30000);

  it("defaults to the 80ms standard cadence, unchanged from before the setting existed", async () => {
    const { container, rerender } = render(<BoardDisplay message="A" isLoading={false} size="md" />, {
      wrapper: TestWrapper,
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(500);
    });

    const reading = await measureCascade(
      container,
      rerender,
      <BoardDisplay message="K" isLoading={false} size="md" />,
      { sampleMs: 2 },
    );

    expect(reading.settleMs).not.toBeNull();
    expect(Math.abs((reading.settleMs as number) - 9 * 80)).toBeLessThanOrEqual(84);
  });
});
