import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import { ColorPickerContent } from "@/components/tiptap-template-editor/components/ColorPickerContent";
import { ThemeProvider } from "@/hooks/use-theme";

// Test wrapper with providers (TooltipProvider is rendered inside ColorPickerContent)
function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="light">
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
}

/**
 * The picker's character-code-62 button (issue #1657).
 *
 * This button was gated on `deviceType === "note"`, which left Flagship owners
 * with no way to insert code 62 from the picker at all — including the owners of
 * 2026-era Flagships whose flap draws a heart. It is now offered for every
 * board; only its wording follows the board, because a degree-flap Flagship must
 * not be handed a button captioned "Heart" that draws a degree sign.
 */
describe("ColorPickerContent code-62 button", () => {
  it("labels it a heart on a Note device", () => {
    render(<ColorPickerContent onInsert={vi.fn()} deviceType="note" />, { wrapper: TestWrapper });

    expect(screen.getByRole("option", { name: "Heart character" })).toBeTruthy();
  });

  it("labels it a heart on a Flagship whose flap carries one", () => {
    render(<ColorPickerContent onInsert={vi.fn()} deviceType="flagship" code62Glyph="heart" />, {
      wrapper: TestWrapper,
    });

    expect(screen.getByRole("option", { name: "Heart character" })).toBeTruthy();
  });

  it("labels it a degree on a Flagship that was not told which flap it has", () => {
    render(<ColorPickerContent onInsert={vi.fn()} deviceType="flagship" />, { wrapper: TestWrapper });

    expect(screen.getByRole("option", { name: "Degree character" })).toBeTruthy();
    expect(screen.queryByRole("option", { name: "Heart character" })).toBeNull();
  });

  it("offers the button to a Flagship at all", () => {
    // The regression itself: the whole control used to be absent here.
    render(<ColorPickerContent onInsert={vi.fn()} deviceType="flagship" />, { wrapper: TestWrapper });

    expect(screen.getByRole("option", { name: "Degree character" })).toBeTruthy();
  });

  it("inserts the degree symbol whichever glyph the board draws", () => {
    // Code 62 is what goes on the wire; the flap decides only what is seen.
    const cases = [
      { deviceType: "note", code62Glyph: undefined, name: "Heart character" },
      { deviceType: "flagship", code62Glyph: undefined, name: "Degree character" },
      { deviceType: "flagship", code62Glyph: "heart", name: "Heart character" },
    ] as const;

    for (const { deviceType, code62Glyph, name } of cases) {
      const onInsert = vi.fn();
      const { unmount } = render(
        <ColorPickerContent onInsert={onInsert} deviceType={deviceType} code62Glyph={code62Glyph} />,
        { wrapper: TestWrapper },
      );

      fireEvent.click(screen.getByRole("option", { name }));
      expect(onInsert).toHaveBeenCalledWith("°");
      unmount();
    }
  });

  it("still shows all color buttons alongside it", () => {
    render(<ColorPickerContent onInsert={vi.fn()} deviceType="note" />, { wrapper: TestWrapper });

    const colors = ["red", "orange", "yellow", "green", "blue", "violet", "white", "black"];
    for (const color of colors) {
      expect(screen.getByRole("option", { name: `${color} color` })).toBeTruthy();
    }
    expect(screen.getByRole("option", { name: "Heart character" })).toBeTruthy();
  });
});
