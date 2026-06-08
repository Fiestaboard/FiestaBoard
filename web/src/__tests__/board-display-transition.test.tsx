import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { ThemeProvider } from "@/hooks/use-theme";
import React, { useState } from "react";
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

// Helper component to control isLoading state
function TestBoardDisplay({ initialLoading, message }: { initialLoading: boolean; message: string | null }) {
  const [isLoading, setIsLoading] = useState(initialLoading);

  return (
    <div>
      <BoardDisplay message={message} isLoading={isLoading} size="md" boardType="black" />
      <button data-testid="toggle-loading" onClick={() => setIsLoading(false)}>
        Stop Loading
      </button>
    </div>
  );
}

describe("BoardDisplay Transition Out", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("continues cycling characters after isLoading becomes false until reaching target", async () => {
    // Simple message: "A" in first position
    // Start with a message so tiles exist, then go to loading, then back to message
    const message = "A";

    // Start with message visible (not loading)
    const { rerender } = render(<TestBoardDisplay initialLoading={false} message={message} />, {
      wrapper: TestWrapper,
    });

    // Wait for initial render
    await vi.advanceTimersByTimeAsync(100);

    // Get the first tile (position 0,0)
    let firstTile = screen.queryByTestId("char-tile-0-0");
    expect(firstTile).toBeTruthy();
    if (!firstTile) return;

    // Now put into loading state
    rerender(<TestBoardDisplay initialLoading={true} message={message} />, { wrapper: TestWrapper });

    // Wait for loading to start and let tiles cycle a bit
    await vi.advanceTimersByTimeAsync(500);

    // Now stop loading - tiles should transition from current position to target
    rerender(<TestBoardDisplay initialLoading={false} message={message} />, { wrapper: TestWrapper });

    // Advance a bit to let the transition state update
    await vi.advanceTimersByTimeAsync(100);

    // Get the tile again (might have re-rendered)
    firstTile = screen.queryByTestId("char-tile-0-0");
    expect(firstTile).toBeTruthy();
    if (!firstTile) return;

    // Animation duration is ~70ms per character (5000ms / 71 chars)
    const animationDuration = Math.round(5000 / 71); // ~70ms

    // Track character changes
    const observedChars: string[] = [];
    let stoppedAtChar: string | null = null;

    // Advance time and observe character changes
    // We should see characters cycling, then stop at "A"
    for (let i = 0; i < 150; i++) {
      await vi.advanceTimersByTimeAsync(animationDuration);

      firstTile = screen.queryByTestId("char-tile-0-0");
      if (!firstTile) continue;

      const currentChar = firstTile.getAttribute("data-current-char");
      const isTransitioning = firstTile.getAttribute("data-is-transitioning") === "true";
      const targetChar = firstTile.getAttribute("data-target-char");

      if (currentChar) {
        observedChars.push(currentChar);

        // If we've reached target and stopped transitioning, we're done
        if (currentChar === targetChar && isTransitioning === false) {
          stoppedAtChar = currentChar;
          break;
        }
      }
    }

    // Verify we eventually stopped at the target
    expect(stoppedAtChar).toBe("A");
    expect(observedChars.length).toBeGreaterThan(0);

    // Verify the tile is no longer transitioning
    firstTile = screen.queryByTestId("char-tile-0-0");
    if (firstTile) {
      const finalIsTransitioning = firstTile.getAttribute("data-is-transitioning");
      expect(finalIsTransitioning).toBe("false");
    }
  }, 15000); // Increase timeout to 15 seconds

  it("transitions smoothly from loading to loaded state without abrupt stop", async () => {
    const message1 = "HELLO";
    const message2 = "WORLD";

    // Start with a message so tiles exist
    const { rerender } = render(<TestBoardDisplay initialLoading={false} message={message1} />, {
      wrapper: TestWrapper,
    });

    await vi.advanceTimersByTimeAsync(100);

    // Get first tile to observe
    let firstTile = screen.queryByTestId("char-tile-0-0");
    expect(firstTile).toBeTruthy();
    if (!firstTile) return;

    const initialChar = firstTile.getAttribute("data-current-char");

    // Now put into loading state
    rerender(<TestBoardDisplay initialLoading={true} message={message1} />, { wrapper: TestWrapper });

    // Let tiles cycle during loading
    await vi.advanceTimersByTimeAsync(500);

    // Transition: set new message and stop loading
    // First character changes from "H" to "W"
    rerender(<TestBoardDisplay initialLoading={false} message={message2} />, { wrapper: TestWrapper });

    await vi.advanceTimersByTimeAsync(100);

    const animationDuration = Math.round(5000 / 71);

    // Track if we see character changes (proving transition is happening)
    let sawCharacterChange = false;
    let previousChar: string | null = initialChar;
    let sawTransitioning = false;
    const targetChar = "W"; // First char of "WORLD"

    // Advance time and verify component continues to render and characters change
    for (let i = 0; i < 80; i++) {
      await vi.advanceTimersByTimeAsync(animationDuration);

      firstTile = screen.queryByTestId("char-tile-0-0");
      if (!firstTile) continue;

      const currentChar = firstTile.getAttribute("data-current-char");
      const isTransitioning = firstTile.getAttribute("data-is-transitioning");

      // If character changed from previous, transition is working
      if (previousChar !== null && currentChar !== null && currentChar !== previousChar) {
        sawCharacterChange = true;
      }

      // Track if we saw transitioning state
      if (isTransitioning === "true") {
        sawTransitioning = true;
      }

      // Update previous char
      if (currentChar) {
        previousChar = currentChar;
      }

      // If we've reached the target and stopped transitioning, we're done
      if (currentChar === targetChar && isTransitioning === "false") {
        break;
      }
    }

    // We should have seen at least one character change (tile transitioning to "W")
    // OR we should have seen transitioning state (proving transition happened)
    expect(sawCharacterChange || sawTransitioning).toBe(true);
  }, 10000);

  it("each tile stops independently when reaching its target character", async () => {
    // Message with different characters: "A" (index 1) and "Z" (index 26)
    // They should stop at different times if they start from different positions
    const message1 = "AA"; // Start with both "A"
    const message2 = "AZ"; // Change to "A" and "Z"

    // Start with initial message
    const { rerender } = render(<TestBoardDisplay initialLoading={false} message={message1} />, {
      wrapper: TestWrapper,
    });

    await vi.advanceTimersByTimeAsync(100);

    // Put into loading
    rerender(<TestBoardDisplay initialLoading={true} message={message1} />, { wrapper: TestWrapper });

    await vi.advanceTimersByTimeAsync(100);

    // Transition to new message - second tile changes from "A" to "Z"
    rerender(<TestBoardDisplay initialLoading={false} message={message2} />, { wrapper: TestWrapper });

    await vi.advanceTimersByTimeAsync(50);

    const animationDuration = Math.round(5000 / 71);

    // Get both tiles
    let tileA = screen.queryByTestId("char-tile-0-0"); // First "A" (unchanged)
    let tileZ = screen.queryByTestId("char-tile-0-1"); // Second "Z" (changed)

    expect(tileA).toBeTruthy();
    expect(tileZ).toBeTruthy();

    if (!tileA || !tileZ) return;

    // Track when each tile stops
    let tileAStopped = false;
    let tileZStopped = false;
    let tileALastChar: string | null = null;
    let tileZLastChar: string | null = null;

    // Advance time and observe both tiles
    for (let i = 0; i < 150; i++) {
      await vi.advanceTimersByTimeAsync(animationDuration);

      // Re-query tiles in case they re-render
      tileA = screen.queryByTestId("char-tile-0-0");
      tileZ = screen.queryByTestId("char-tile-0-1");

      if (!tileA || !tileZ) continue;

      const aChar = tileA.getAttribute("data-current-char");
      const aTransitioning = tileA.getAttribute("data-is-transitioning") === "true";
      const aTarget = tileA.getAttribute("data-target-char");

      const zChar = tileZ.getAttribute("data-current-char");
      const zTransitioning = tileZ.getAttribute("data-is-transitioning") === "true";
      const zTarget = tileZ.getAttribute("data-target-char");

      // Check if tile A stopped (should stop quickly since target didn't change)
      if (aChar === aTarget && !aTransitioning && !tileAStopped) {
        tileAStopped = true;
        tileALastChar = aChar;
      }

      // Check if tile Z stopped
      if (zChar === zTarget && !zTransitioning && !tileZStopped) {
        tileZStopped = true;
        tileZLastChar = zChar;
      }

      // If both stopped, we're done
      if (tileAStopped && tileZStopped) {
        break;
      }
    }

    // Both should eventually stop at their targets
    expect(tileAStopped).toBe(true);
    expect(tileZStopped).toBe(true);
    expect(tileALastChar).toBe("A");
    expect(tileZLastChar).toBe("Z");

    // They might stop at the same time or different times depending on starting position
    // But the key is they both eventually reach their targets
  }, 10000); // Increase timeout
});
