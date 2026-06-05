import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { ThemeProvider } from "next-themes";
import React from "react";
import { describe, expect, it, vi } from "vitest";

import { ColorPickerContent } from "@/components/tiptap-template-editor/components/ColorPickerContent";

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

describe("ColorPickerContent heart button for Note device", () => {
  it("shows heart button when deviceType is 'note'", () => {
    const onInsert = vi.fn();
    render(<ColorPickerContent onInsert={onInsert} deviceType="note" />, { wrapper: TestWrapper });

    const heartButton = screen.getByRole("option", { name: "Heart character" });
    expect(heartButton).toBeTruthy();
  });

  it("does not show heart button when deviceType is 'flagship'", () => {
    const onInsert = vi.fn();
    render(<ColorPickerContent onInsert={onInsert} deviceType="flagship" />, { wrapper: TestWrapper });

    const heartButton = screen.queryByRole("option", { name: "Heart character" });
    expect(heartButton).toBeNull();
  });

  it("does not show heart button when deviceType is not provided", () => {
    const onInsert = vi.fn();
    render(<ColorPickerContent onInsert={onInsert} />, { wrapper: TestWrapper });

    const heartButton = screen.queryByRole("option", { name: "Heart character" });
    expect(heartButton).toBeNull();
  });

  it("calls onInsert with degree symbol (renders as heart on Note device) when heart button is clicked", () => {
    const onInsert = vi.fn();
    render(<ColorPickerContent onInsert={onInsert} deviceType="note" />, { wrapper: TestWrapper });

    const heartButton = screen.getByRole("option", { name: "Heart character" });
    fireEvent.click(heartButton);

    expect(onInsert).toHaveBeenCalledWith("°");
  });

  it("still shows all color buttons alongside heart button for Note", () => {
    const onInsert = vi.fn();
    render(<ColorPickerContent onInsert={onInsert} deviceType="note" />, { wrapper: TestWrapper });

    // All standard colors should still be present
    const colors = ["red", "orange", "yellow", "green", "blue", "violet", "white", "black"];
    for (const color of colors) {
      const button = screen.getByRole("option", { name: `${color} color` });
      expect(button).toBeTruthy();
    }

    // Heart should also be present
    const heartButton = screen.getByRole("option", { name: "Heart character" });
    expect(heartButton).toBeTruthy();
  });
});
