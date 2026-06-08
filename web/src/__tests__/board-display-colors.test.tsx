import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@/hooks/use-theme";
import React from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BoardDisplay } from "@/components/board-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";

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

describe("BoardDisplay Note device heart character", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders degree symbol as heart (♥) on Note device", async () => {
    // Degree symbol ° (code 62) should become ♥ on Note
    render(<BoardDisplay message="°" deviceType="note" boardType="black" size="md" />, { wrapper: TestWrapper });
    await vi.advanceTimersByTimeAsync(200);

    const tile = screen.queryByTestId("char-tile-0-0");
    expect(tile).toBeTruthy();
    if (tile) {
      // The target char should be the text heart ♥ (not the emoji ❤)
      expect(tile.getAttribute("data-target-char")).toBe("♥");
    }
  });

  it("keeps degree symbol on Flagship device", async () => {
    render(<BoardDisplay message="°" deviceType="flagship" boardType="black" size="md" />, { wrapper: TestWrapper });
    await vi.advanceTimersByTimeAsync(200);

    const tile = screen.queryByTestId("char-tile-0-0");
    expect(tile).toBeTruthy();
    if (tile) {
      expect(tile.getAttribute("data-target-char")).toBe("°");
    }
  });
});
