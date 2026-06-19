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

describe("ScaledBoardDisplay preview-size toggle", () => {
  beforeEach(() => {
    window.sessionStorage.clear();
  });
  afterEach(() => {
    window.sessionStorage.clear();
  });

  it("renders no toggle for a flagship device", () => {
    render(<ScaledBoardDisplay message="" deviceType="flagship" isStatic />, { wrapper: TestWrapper });
    expect(screen.queryByRole("button", { name: "Fit" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Actual size" })).toBeNull();
  });

  it("renders no toggle for a note device", () => {
    render(<ScaledBoardDisplay message="" deviceType="note" isStatic />, { wrapper: TestWrapper });
    expect(screen.queryByRole("group", { name: "Preview size" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Fit" })).toBeNull();
  });

  it("renders the toggle for a note_array device", () => {
    render(<ScaledBoardDisplay message="" deviceType="note_array" notesWide={4} notesTall={1} isStatic />, {
      wrapper: TestWrapper,
    });
    expect(screen.getByRole("group", { name: "Preview size" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Fit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Actual size" })).toBeInTheDocument();
  });

  it("defaults to fit mode (no scroll container) when nothing is persisted", () => {
    const { container } = render(
      <ScaledBoardDisplay message="" deviceType="note_array" notesWide={4} notesTall={1} isStatic />,
      { wrapper: TestWrapper },
    );
    expect(container.querySelector("[data-testid='actual-size-scroll']")).toBeNull();
    expect(screen.getByRole("button", { name: "Fit" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Actual size" })).toHaveAttribute("aria-pressed", "false");
  });

  it("switches to actual mode, shows the scroll container, and persists to sessionStorage", () => {
    const { container } = render(
      <ScaledBoardDisplay message="" deviceType="note_array" notesWide={4} notesTall={1} isStatic />,
      { wrapper: TestWrapper },
    );

    fireEvent.click(screen.getByRole("button", { name: "Actual size" }));

    const scroll = container.querySelector("[data-testid='actual-size-scroll']") as HTMLElement | null;
    expect(scroll).not.toBeNull();
    // Tailwind `overflow-x-auto` → CSS `overflow-x: auto` on the scroll container.
    expect(scroll).toHaveClass("overflow-x-auto");
    expect(screen.getByRole("button", { name: "Actual size" })).toHaveAttribute("aria-pressed", "true");
    expect(window.sessionStorage.getItem(MODE_STORAGE_KEY)).toBe("actual");
  });

  it("switches back to fit mode and persists it", () => {
    const { container } = render(
      <ScaledBoardDisplay message="" deviceType="note_array" notesWide={4} notesTall={1} isStatic />,
      { wrapper: TestWrapper },
    );

    fireEvent.click(screen.getByRole("button", { name: "Actual size" }));
    expect(container.querySelector("[data-testid='actual-size-scroll']")).not.toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Fit" }));
    expect(container.querySelector("[data-testid='actual-size-scroll']")).toBeNull();
    expect(window.sessionStorage.getItem(MODE_STORAGE_KEY)).toBe("fit");
  });

  it("reads the persisted mode back on re-mount", () => {
    window.sessionStorage.setItem(MODE_STORAGE_KEY, "actual");
    const { container } = render(
      <ScaledBoardDisplay message="" deviceType="note_array" notesWide={4} notesTall={1} isStatic />,
      { wrapper: TestWrapper },
    );
    expect(container.querySelector("[data-testid='actual-size-scroll']")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Actual size" })).toHaveAttribute("aria-pressed", "true");
  });

  it("ignores a persisted 'actual' mode for flagship boards (always fit, no toggle)", () => {
    window.sessionStorage.setItem(MODE_STORAGE_KEY, "actual");
    const { container } = render(<ScaledBoardDisplay message="" deviceType="flagship" isStatic />, {
      wrapper: TestWrapper,
    });
    // No toggle and no scroll container — flagship rendering is unchanged.
    expect(screen.queryByRole("group", { name: "Preview size" })).toBeNull();
    expect(container.querySelector("[data-testid='actual-size-scroll']")).toBeNull();
  });
});
