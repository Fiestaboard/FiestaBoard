import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TemplateEditorToolbar } from "@/components/tiptap-template-editor/components/TemplateEditorToolbar";

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = (await importOriginal()) as Record<string, unknown>;
  return {
    ...mod,
    api: {
      ...(mod.api as Record<string, unknown>),
      getTemplateVariables: vi.fn().mockResolvedValue({ variables: { x: {} }, colors: { red: 63 }, formatting: {} }),
    },
  };
});

function renderToolbar(props: Record<string, unknown>) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TemplateEditorToolbar editor={null} {...props} />
    </QueryClientProvider>,
  );
}

describe("TemplateEditorToolbar draw mode", () => {
  it("renders the pencil toggle and fires it", () => {
    const onDrawModeToggle = vi.fn();
    renderToolbar({ drawMode: false, onDrawModeToggle, drawBrush: "red", onDrawBrushChange: vi.fn() });
    const toggle = screen.getByTestId("draw-mode-toggle");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(onDrawModeToggle).toHaveBeenCalled();
  });

  it("shows brush dropdown and disables editing controls in draw mode", () => {
    renderToolbar({ drawMode: true, onDrawModeToggle: vi.fn(), drawBrush: "red", onDrawBrushChange: vi.fn() });
    expect(screen.getByTestId("draw-mode-toggle")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("draw-brush-dropdown")).toBeInTheDocument();
    expect(screen.getByLabelText("Cut")).toBeDisabled();
    expect(screen.getByLabelText("Paste")).toBeDisabled();
  });

  it("hides the pencil when no handler is provided", () => {
    renderToolbar({});
    expect(screen.queryByTestId("draw-mode-toggle")).toBeNull();
  });
});
