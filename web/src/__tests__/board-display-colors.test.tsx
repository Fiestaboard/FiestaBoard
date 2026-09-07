import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BoardDisplay } from "@/components/board-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

// Test wrapper with providers
function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
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

describe("BoardDisplay white/black tile colors", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders white color tile as white on black board", async () => {
    // {white} is color code 69
    render(<BoardDisplay message="{white}" boardType="black" size="md" />, { wrapper: TestWrapper });
    await vi.advanceTimersByTimeAsync(200);

    const tile = screen.queryByTestId("char-tile-0-0");
    expect(tile).toBeTruthy();
    // On black board, white tile should have a white-ish background
    // The color tile renders as an inner div; the tile itself has the default background
  });

  it("renders white color tile as black on white board (inverted)", async () => {
    render(<BoardDisplay message="{white}" boardType="white" size="md" />, { wrapper: TestWrapper });
    await vi.advanceTimersByTimeAsync(200);

    const tile = screen.queryByTestId("char-tile-0-0");
    expect(tile).toBeTruthy();
    // On white board, the "white" color tile (69) should be inverted to black
  });

  it("renders black color tile as black on black board", async () => {
    render(<BoardDisplay message="{black}" boardType="black" size="md" />, { wrapper: TestWrapper });
    await vi.advanceTimersByTimeAsync(200);

    const tile = screen.queryByTestId("char-tile-0-0");
    expect(tile).toBeTruthy();
  });

  it("renders black color tile as white on white board (inverted)", async () => {
    render(<BoardDisplay message="{black}" boardType="white" size="md" />, { wrapper: TestWrapper });
    await vi.advanceTimersByTimeAsync(200);

    const tile = screen.queryByTestId("char-tile-0-0");
    expect(tile).toBeTruthy();
  });
});

/**
 * Character code 62 is one code with two possible physical flaps (issue #1657).
 *
 * Note hardware has only ever carried the heart. Flagships carried the degree
 * sign until 2026, when Vestaboard replaced it with a heart on newly
 * manufactured units — so `deviceType` no longer decides what a Flagship draws,
 * and the board's own `code62Glyph` does.
 */
describe("BoardDisplay code-62 flap", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  /** Render one board and return the glyph its first tile drew. */
  async function firstTileGlyph(props: Partial<Parameters<typeof BoardDisplay>[0]>) {
    render(<BoardDisplay message="°" boardType="black" size="md" {...props} />, { wrapper: TestWrapper });
    await vi.advanceTimersByTimeAsync(200);
    const tile = screen.getByTestId("char-tile-0-0");
    return tile.getAttribute("data-target-char");
  }

  it("draws a heart on a Note device", async () => {
    // The text heart ♥, not the emoji ❤.
    expect(await firstTileGlyph({ deviceType: "note" })).toBe("♥");
  });

  it("draws a degree on a Flagship that was not told which flap it has", async () => {
    // The promise to every install that predates the setting: unchanged.
    expect(await firstTileGlyph({ deviceType: "flagship" })).toBe("°");
  });

  it("draws a heart on a Flagship whose flap carries one", async () => {
    // The reported bug: a 2026-era Flagship previewing 72° while showing 72♥.
    expect(await firstTileGlyph({ deviceType: "flagship", code62Glyph: "heart" })).toBe("♥");
  });

  it("draws a degree on a Flagship explicitly set to the degree flap", async () => {
    expect(await firstTileGlyph({ deviceType: "flagship", code62Glyph: "degree" })).toBe("°");
  });

  it("ignores a stale Flagship setting on a Note device", async () => {
    // Note flaps only ever carried the heart, so the setting is not the
    // device's to answer — a board switched Flagship→Note keeps the old value.
    expect(await firstTileGlyph({ deviceType: "note", code62Glyph: "degree" })).toBe("♥");
  });
});
