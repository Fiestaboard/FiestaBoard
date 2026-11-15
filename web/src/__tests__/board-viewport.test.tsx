import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import React from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { BoardViewport, boardViewportHint, useBoardViewportLabels } from "@/components/board-viewport";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
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

/** Captures the labels object the hook builds, for the copy assertions. */
function LabelsProbe({ region, onLabels }: { region?: string; onLabels: (l: unknown) => void }) {
  onLabels(useBoardViewportLabels(region));
  return null;
}

type Labels = ReturnType<typeof useBoardViewportLabels>;

function labelsFor(region?: string): Labels {
  let captured: Labels | undefined;
  render(<LabelsProbe region={region} onLabels={(l) => (captured = l as Labels)} />, { wrapper: TestWrapper });
  return captured!;
}

describe("BoardViewport (app wrapper)", () => {
  beforeEach(() => window.sessionStorage.clear());
  afterEach(() => window.sessionStorage.clear());

  it("renders the FiestaUI viewport in Actual size by default", () => {
    const { container } = render(<BoardViewport message="HELLO" deviceType="flagship" isStatic />, {
      wrapper: TestWrapper,
    });
    const root = container.querySelector("[data-slot=board-viewport]");
    expect(root).not.toBeNull();
    expect(root).toHaveAttribute("data-mode", "actual");
  });

  it("names the region with the app's translated preview label", () => {
    render(<BoardViewport message="HELLO" deviceType="flagship" isStatic />, { wrapper: TestWrapper });
    expect(screen.getByRole("group", { name: "Board preview" })).toBeInTheDocument();
  });

  it("lets a list name each board's region", () => {
    render(<BoardViewport message="HELLO" deviceType="flagship" isStatic regionLabel="Kitchen preview" />, {
      wrapper: TestWrapper,
    });
    expect(screen.getByRole("group", { name: "Kitchen preview" })).toBeInTheDocument();
  });

  it("names the board with the app's withMessage translation (shared chrome)", () => {
    render(<BoardViewport message="HELLO" deviceType="flagship" />, { wrapper: TestWrapper });
    expect(screen.getByRole("img", { name: /Board display: HELLO/ })).toBeInTheDocument();
  });

  it("keeps the session's stored Fit choice (persist)", () => {
    window.sessionStorage.setItem("fiestaboard:boardPreviewMode", "fit");
    const { container } = render(<BoardViewport message="" deviceType="note_array" notesWide={3} isStatic />, {
      wrapper: TestWrapper,
    });
    expect(container.querySelector("[data-slot=board-viewport]")).toHaveAttribute("data-mode", "fit");
  });
});

describe("useBoardViewportLabels", () => {
  it("translates the indicator copy (07 57:27771, 02 36:35275)", () => {
    const l = labelsFor();
    expect(l.region).toBe("Board preview");
    expect(l.previewSize).toBe("Preview size");
    expect(l.fit).toBe("Fit");
    expect(l.actual).toBe("Actual size");
    expect(l.note(1, 3)).toBe("Note 1 of 3");
    expect(l.arrayColumn(1, 2, 4)).toBe("Column 1 of 2 · 4 notes");
    expect(l.columns(1, 16, 22)).toBe("Columns 1–16 of 22");
    expect(l.overview(3, 45)).toBe("Overview · 3 notes · tap Actual to read");
    expect(l.overview(null, 22)).toBe("Overview · 22 columns · tap Actual to read");
  });

  it("uses a caller's region name", () => {
    expect(labelsFor("Lobby wall preview").region).toBe("Lobby wall preview");
  });
});

describe("boardViewportHint", () => {
  const t = (key: string) => key;

  it("gives a note array the 07 keyboard hint that snaps to each Note", () => {
    expect(boardViewportHint(t, "note_array", false)).toBe("viewportHintNotes");
  });

  it("gives any other board the keyboard hint that snaps to each column", () => {
    expect(boardViewportHint(t, "flagship", false)).toBe("viewportHintColumns");
    expect(boardViewportHint(t, undefined, false)).toBe("viewportHintColumns");
  });

  it("says 'swipe' on a coarse pointer (02)", () => {
    expect(boardViewportHint(t, "note_array", true)).toBe("viewportHintTouch");
    expect(boardViewportHint(t, "flagship", true)).toBe("viewportHintTouch");
  });
});
