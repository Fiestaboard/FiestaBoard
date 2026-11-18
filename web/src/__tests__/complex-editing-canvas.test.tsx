import { act, fireEvent, render, renderHook, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { CanvasDrawTab } from "@/components/canvas-editor/canvas-draw-tab";
import { CanvasLayers, describeShape, shapeIsBound } from "@/components/complex-editing/canvas-layers";
import { useCanvasHistory } from "@/components/complex-editing/use-canvas-history";
import type { CanvasContent, CanvasShape } from "@/lib/api";

const t = (key: string, params?: Record<string, unknown>) => `${key}:${JSON.stringify(params ?? {})}`;

describe("describeShape / shapeIsBound", () => {
  it("names shapes by type and position and spells their geometry", () => {
    expect(describeShape({ type: "rect", x: 30, y: 26, w: 14, h: 8 }, 0, t)).toEqual({
      name: 'layerRect:{"n":1}',
      meta: 'layerMetaBox:{"x":"30","y":"26","w":"14","h":"8"}',
    });
    expect(describeShape({ type: "text", x: 2, y: 24, text: "64°", color: "#fff", font: "5x7" }, 3, t).name).toBe(
      'layerTextNamed:{"text":"64°"}',
    );
    expect(
      describeShape({ type: "text", x: 2, y: 24, text: "{{weather.temperature}}", color: "#fff" }, 3, t).name,
    ).toBe('layerText:{"n":4}');
    expect(describeShape({ type: "circle", cx: "{{sun.x}}", cy: 5, r: 4 }, 1, t).meta).toContain('"x":"ƒ"');
  });

  it("marks shapes that draw from data", () => {
    expect(shapeIsBound({ type: "rect", x: 0, y: 0, w: 1, h: 1 })).toBe(false);
    expect(shapeIsBound({ type: "rect", x: 0, y: 0, w: 1, h: 1, if: false })).toBe(false);
    expect(shapeIsBound({ type: "circle", cx: 1, cy: 1, r: 1, if: "{{weather.is_day}}" })).toBe(true);
    expect(shapeIsBound({ type: "line", x1: 0, y1: 0, x2: "{{x}}", y2: 1, stroke: "#fff" })).toBe(true);
    expect(shapeIsBound({ type: "rect", x: 0, y: 0, w: 1, h: 1, foreach: "{{items}}" })).toBe(true);
  });
});

describe("CanvasLayers", () => {
  const shapes: CanvasShape[] = [
    { type: "gradient", from: "#000", to: "#f80" },
    { type: "circle", cx: 40, cy: 10, r: 8, if: "{{weather.is_day}}" },
    { type: "text", x: 2, y: 24, text: "64°", color: "#fff" },
  ];

  it("lists shapes front to back with bound ones marked", () => {
    render(<CanvasLayers canvasId="sky" shapes={shapes} onShapesChange={vi.fn()} />);
    const list = screen.getByRole("list", { name: "Layers · sky" });
    const names = within(list)
      .getAllByRole("listitem")
      .map((item) => item.textContent ?? "");
    expect(names[0]).toContain("Text · 64°");
    expect(names[1]).toContain("Circle 2");
    expect(names[1]).toContain("Data");
    expect(names[2]).toContain("Gradient 1");
  });

  it("reorders shapes back into draw order", async () => {
    const onShapesChange = vi.fn();
    render(<CanvasLayers canvasId="sky" shapes={shapes} onShapesChange={onShapesChange} />);
    const items = within(screen.getByRole("list", { name: "Layers · sky" })).getAllByRole("listitem");
    items[0].focus();
    await userEvent.keyboard(" ");
    await userEvent.keyboard("{ArrowDown}");
    await userEvent.keyboard(" ");
    expect(onShapesChange).toHaveBeenCalledWith([shapes[0], shapes[2], shapes[1]]);
  });

  it("renders nothing for a canvas without shapes", () => {
    const { container } = render(<CanvasLayers canvasId="sky" shapes={[]} onShapesChange={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("useCanvasHistory", () => {
  it("undoes and redoes committed content one step at a time", () => {
    const onChange = vi.fn();
    const a: CanvasContent = { pixels: ["a"] };
    const b: CanvasContent = { pixels: ["b"] };
    const { result, rerender } = renderHook(({ content }) => useCanvasHistory(content, onChange), {
      initialProps: { content: a as CanvasContent | null },
    });
    expect(result.current.canUndo).toBe(false);
    act(() => result.current.commit(b));
    expect(onChange).toHaveBeenLastCalledWith(b);
    rerender({ content: b });
    expect(result.current.canUndo).toBe(true);
    act(() => result.current.undo());
    expect(onChange).toHaveBeenLastCalledWith(a);
    rerender({ content: a });
    expect(result.current.canRedo).toBe(true);
    act(() => result.current.redo());
    expect(onChange).toHaveBeenLastCalledWith(b);
    rerender({ content: b });
    expect(result.current.canRedo).toBe(false);
  });

  it("ignores undo and redo with nothing to step to", () => {
    const onChange = vi.fn();
    const { result } = renderHook(() => useCanvasHistory(null, onChange));
    act(() => {
      result.current.undo();
      result.current.redo();
    });
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("CanvasDrawTab tool rail", () => {
  function Draw({ spy }: { spy: (c: CanvasContent) => void }) {
    const [content, setContent] = useState<CanvasContent | null>(null);
    return (
      <CanvasDrawTab
        content={content}
        width={4}
        height={2}
        onContentChange={(c) => {
          spy(c);
          setContent(c);
        }}
      />
    );
  }

  it("chooses pad tools from the kit rail and undoes a stroke", async () => {
    const spy = vi.fn();
    render(<Draw spy={spy} />);
    const rail = screen.getByRole("group", { name: "Canvas tools" });
    expect(within(rail).getByRole("button", { name: "Brush" })).toHaveAttribute("aria-pressed", "true");
    expect(within(rail).queryByRole("button", { name: "Rectangle" })).toBeNull();
    const undo = within(rail).getByRole("button", { name: "Undo" });
    expect(undo).toBeDisabled();
    fireEvent.keyDown(screen.getByTestId("pixel-pad"), { key: " " });
    expect(spy.mock.calls.at(-1)![0].pixels[0][0]).not.toBe(".");
    expect(undo).toBeEnabled();
    await userEvent.click(undo);
    expect(spy.mock.calls.at(-1)![0]).toEqual({});
    await userEvent.click(within(rail).getByRole("button", { name: "Eraser" }));
    expect(within(rail).getByRole("button", { name: "Eraser" })).toHaveAttribute("aria-pressed", "true");
  });
});
