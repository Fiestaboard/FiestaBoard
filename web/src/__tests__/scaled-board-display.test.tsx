import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

const MODE_STORAGE_KEY = "fiestaboard:boardPreviewMode";

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

/**
 * Slice 2.4 (WEB-07): the app's board wrapper renders FiestaUI BoardViewport, so a
 * board keeps its real tiles and scrolls instead of shrinking (owner rule 9), and
 * Actual size is the default for every board type. Thumbnails opt out with
 * `thumbnail` and stay a fit-scaled picture that never touches the session mode.
 *
 * jsdom has no layout, so these pin the wiring; the scroll, snap, keys and the Fit
 * overview are exercised in a real browser by tests/layout/board-viewport.spec.ts.
 */
describe("ScaledBoardDisplay renders BoardViewport (boards never shrink)", () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => window.sessionStorage.clear());

  it.each(["flagship", "note", "note_array"] as const)(
    "draws a %s board in a BoardViewport, Actual size",
    (deviceType) => {
      const { container } = render(<ScaledBoardDisplay message="" deviceType={deviceType} isStatic />, {
        wrapper: TestWrapper,
      });
      const viewport = container.querySelector("[data-slot=board-viewport]");
      expect(viewport).not.toBeNull();
      expect(viewport).toHaveAttribute("data-mode", "actual");
      // The old fit wrapper's scale box is gone.
      expect(container.querySelector("[data-testid='actual-size-scroll']")).toBeNull();
    },
  );

  it("draws the board without its own bezel: the viewport's bezel clips the scroll", () => {
    const { container } = render(<ScaledBoardDisplay message="" deviceType="flagship" isStatic />, {
      wrapper: TestWrapper,
    });
    expect(container.querySelector("[data-slot=board-viewport-bezel] [data-slot=board-display]")).not.toBeNull();
  });

  it("starts from the session's stored choice (a Fit tap lasts the session)", () => {
    window.sessionStorage.setItem(MODE_STORAGE_KEY, "fit");
    const { container } = render(<ScaledBoardDisplay message="" deviceType="flagship" isStatic />, {
      wrapper: TestWrapper,
    });
    expect(container.querySelector("[data-slot=board-viewport]")).toHaveAttribute("data-mode", "fit");
  });

  it("passes a region name through for lists", () => {
    render(<ScaledBoardDisplay message="" deviceType="flagship" isStatic regionLabel="Kitchen preview" />, {
      wrapper: TestWrapper,
    });
    expect(screen.getByRole("group", { name: "Kitchen preview" })).toBeInTheDocument();
  });
});

describe("ScaledBoardDisplay thumbnail", () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => window.sessionStorage.clear());

  it("is not a viewport: no scroll region, no keys", () => {
    const { container } = render(<ScaledBoardDisplay thumbnail message="" deviceType="flagship" isStatic />, {
      wrapper: TestWrapper,
    });
    expect(container.querySelector("[data-slot=board-viewport]")).toBeNull();
    expect(container.querySelector("[data-slot=board-display]")).not.toBeNull();
  });

  it("stays fit even when the session stored Actual size", () => {
    window.sessionStorage.setItem(MODE_STORAGE_KEY, "actual");
    const { container } = render(
      <ScaledBoardDisplay thumbnail message="" deviceType="note_array" notesWide={4} notesTall={1} isStatic />,
      { wrapper: TestWrapper },
    );
    expect(container.querySelector("[data-testid='actual-size-scroll']")).toBeNull();
    expect(screen.getByRole("button", { name: "Fit" })).toHaveAttribute("aria-pressed", "true");
  });

  it("never writes the session mode", () => {
    render(<ScaledBoardDisplay thumbnail message="" deviceType="note_array" notesWide={4} notesTall={1} isStatic />, {
      wrapper: TestWrapper,
    });
    fireEvent.click(screen.getByRole("button", { name: "Actual size" }));
    expect(window.sessionStorage.getItem(MODE_STORAGE_KEY)).toBeNull();
  });
});
