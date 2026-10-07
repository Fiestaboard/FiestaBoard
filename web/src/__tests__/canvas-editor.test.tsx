/**
 * The page editor's pixel canvas panel (design PIXEL_CANVAS.md §5): the
 * canvases list, area / bleed / scale / text controls, the Draw tab's pixel
 * pad, the Shapes list + JSON editor, and the Source picker.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { type ReactNode, useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CanvasDrawTab } from "@/components/canvas-editor/canvas-draw-tab";
import { CanvasShapesEditor } from "@/components/canvas-editor/canvas-shapes-editor";
import { CanvasSourcePicker } from "@/components/canvas-editor/canvas-source-picker";
import { CanvasesPanel } from "@/components/canvas-editor/canvases-panel";
import type { Canvas, CanvasContent, CanvasShape, TemplateVariables } from "@/lib/api";
import { api } from "@/lib/api";
import { makeCanvas } from "@/lib/canvas-editing";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual("@/lib/api");
  return { ...actual, api: { ...(actual as { api: object }).api, getTemplateVariables: vi.fn() } };
});

const VARIABLES = {
  variables: { art: ["canvas", "title"], weather: ["temp"] },
  max_lengths: {},
  variable_metadata: {
    art: { canvas: { description: "Scene", format: "canvas" }, title: { description: "Title" } },
    weather: { temp: { description: "Temperature" } },
  },
  colors: {},
  symbols: [],
  filters: [],
  formatting: {},
  syntax_examples: {},
} as unknown as TemplateVariables;

function wrap(children: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const PIXOO = { width: 64, height: 64, font: "3x5" as const };

/** The panel with its canvases held in state, as the page editor holds them. */
function Panel({ initial = [], spy }: { initial?: Canvas[]; spy: (c: Canvas[]) => void }) {
  const [canvases, setCanvases] = useState<Canvas[]>(initial);
  return wrap(
    <CanvasesPanel
      canvases={canvases}
      onChange={(next) => {
        spy(next);
        setCanvases(next);
      }}
      gridRows={10}
      gridCols={16}
      board={PIXOO}
      issues={[]}
      error={null}
    />,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getTemplateVariables).mockResolvedValue(VARIABLES);
});

describe("CanvasesPanel", () => {
  it("adds a canvas over the top-left half of the grid", async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Panel spy={spy} />);
    await user.click(screen.getByRole("button", { name: "Add canvas" }));
    expect(spy).toHaveBeenLastCalledWith([
      expect.objectContaining({ id: "canvas1", area: { row: 1, col: 1, rows: 5, cols: 8 }, text: "hide" }),
    ]);
    expect(screen.getByTestId("canvas-editor-canvas1")).toBeInTheDocument();
  });

  it("edits the area from the row / column fields", async () => {
    const spy = vi.fn();
    render(<Panel spy={spy} initial={[makeCanvas("sky", { row: 1, col: 1, rows: 2, cols: 2 })]} />);
    fireEvent.change(screen.getByLabelText("Columns"), { target: { value: "6" } });
    expect(spy.mock.calls.at(-1)![0][0].area).toEqual({ row: 1, col: 1, rows: 2, cols: 6 });
  });

  it("sets bleed sides, scale and text flow", async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Panel spy={spy} initial={[makeCanvas("sky", { row: 1, col: 1, rows: 2, cols: 2 })]} />);
    await user.click(screen.getByLabelText("Top"));
    expect(spy.mock.calls.at(-1)![0][0].bleed).toEqual(["top"]);
    await user.click(screen.getByRole("button", { name: "Flow around" }));
    expect(spy.mock.calls.at(-1)![0][0].text).toBe("flow");
  });

  it("renames a canvas only to a valid, unused id", async () => {
    const spy = vi.fn();
    render(
      <Panel
        spy={spy}
        initial={[
          makeCanvas("sky", { row: 1, col: 1, rows: 1, cols: 1 }),
          makeCanvas("sea", { row: 2, col: 1, rows: 1, cols: 1 }),
        ]}
      />,
    );
    const id = screen.getByLabelText("Canvas ID");
    fireEvent.change(id, { target: { value: "sea" } });
    expect(spy).not.toHaveBeenCalled();
    expect(id).toHaveAttribute("aria-invalid", "true");
    fireEvent.change(id, { target: { value: "Bad Id" } });
    expect(spy).not.toHaveBeenCalled();
    fireEvent.change(id, { target: { value: "sun" } });
    expect(spy.mock.calls.at(-1)![0].map((c: Canvas) => c.id)).toEqual(["sun", "sea"]);
  });

  it("deletes the canvas being edited", async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Panel spy={spy} initial={[makeCanvas("sky", { row: 1, col: 1, rows: 1, cols: 1 })]} />);
    await user.click(screen.getByRole("button", { name: "Delete canvas sky" }));
    expect(spy).toHaveBeenLastCalledWith([]);
    expect(screen.getByText("No canvases yet.")).toBeInTheDocument();
  });

  it("stops adding at 8 canvases", () => {
    const eight = Array.from({ length: 8 }, (_, i) => makeCanvas(`c${i}`, { row: 1, col: 1, rows: 1, cols: 1 }));
    render(<Panel spy={vi.fn()} initial={eight} />);
    expect(screen.getByRole("button", { name: "Add canvas" })).toBeDisabled();
  });

  it("shows the server's refusal and the canvas issues", () => {
    render(
      wrap(
        <CanvasesPanel
          canvases={[makeCanvas("sky", { row: 1, col: 1, rows: 1, cols: 1 })]}
          onChange={vi.fn()}
          gridRows={10}
          gridCols={16}
          board={PIXOO}
          issues={[{ canvas_id: "sky", path: "source", message: "nope.canvas is not defined" }]}
          error="shapes[0].x must be a number"
        />,
      ),
    );
    expect(screen.getByTestId("canvas-error")).toHaveTextContent("shapes[0].x must be a number");
    expect(screen.getByTestId("canvas-issues")).toHaveTextContent("sky · source: nope.canvas is not defined");
  });
});

describe("CanvasDrawTab (pixel pad)", () => {
  function Draw({ spy, initial = null }: { spy: (c: CanvasContent) => void; initial?: CanvasContent | null }) {
    const [content, setContent] = useState<CanvasContent | null>(initial);
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

  it("paints from the keyboard: arrows move the cursor, Space paints, pixels + palette are written", () => {
    const spy = vi.fn();
    render(<Draw spy={spy} />);
    const pad = screen.getByRole("application", { name: "Pixel pad, 4 by 2 pixels" });
    pad.focus();
    fireEvent.keyDown(pad, { key: "ArrowRight" });
    fireEvent.keyDown(pad, { key: "ArrowDown" });
    fireEvent.keyDown(pad, { key: " " });
    const content: CanvasContent = spy.mock.calls.at(-1)![0];
    expect(content.size).toEqual([4, 2]);
    expect(content.pixels).toHaveLength(2);
    const key = content.pixels![1][1];
    expect(content.pixels).toEqual(["....", `.${key}..`]);
    expect(content.palette).toEqual({ [key]: "#ff0000" });
    expect(screen.getByTestId("pixel-pad-cursor")).toHaveTextContent("Pixel 2, 2: #ff0000");
  });

  it("paints with the pointer in the chosen colour", () => {
    const spy = vi.fn();
    render(<Draw spy={spy} />);
    fireEvent.change(screen.getByLabelText("Hex colour"), { target: { value: "#00ff00" } });
    const pad = screen.getByTestId("pixel-pad");
    // Zoom 8: pixel (2, 0) spans x 16..23.
    fireEvent.pointerDown(pad, { clientX: 17, clientY: 3, pointerId: 1 });
    fireEvent.pointerMove(pad, { clientX: 25, clientY: 3, pointerId: 1 });
    fireEvent.pointerUp(pad, { pointerId: 1 });
    const content: CanvasContent = spy.mock.calls.at(-1)![0];
    const key = Object.keys(content.palette!)[0];
    expect(content.palette).toEqual({ [key]: "#00ff00" });
    expect(content.pixels).toEqual([`..${key}${key}`, "...."]);
  });

  it("erases, fills and picks colours", async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Draw spy={spy} initial={{ size: [4, 2], palette: { a: "#123456" }, pixels: ["a...", "...."] }} />);
    const pad = screen.getByTestId("pixel-pad");

    await user.click(screen.getByRole("button", { name: "Fill" }));
    fireEvent.pointerDown(pad, { clientX: 20, clientY: 3, pointerId: 1 });
    fireEvent.pointerUp(pad, { pointerId: 1 });
    let content: CanvasContent = spy.mock.calls.at(-1)![0];
    const red = Object.entries(content.palette!).find(([, v]) => v === "#ff0000")![0];
    expect(content.pixels).toEqual([`a${red}${red}${red}`, red.repeat(4)]);

    await user.click(screen.getByRole("button", { name: "Eyedropper" }));
    fireEvent.pointerDown(pad, { clientX: 1, clientY: 1, pointerId: 1 });
    fireEvent.pointerUp(pad, { pointerId: 1 });
    expect(screen.getByLabelText("Hex colour")).toHaveValue("#123456");

    await user.click(screen.getByRole("button", { name: "Eraser" }));
    fireEvent.pointerDown(pad, { clientX: 1, clientY: 1, pointerId: 1 });
    fireEvent.pointerUp(pad, { pointerId: 1 });
    content = spy.mock.calls.at(-1)![0];
    expect(content.pixels![0][0]).toBe(".");
    expect(Object.values(content.palette!)).toEqual(["#ff0000"]);
  });
});

describe("CanvasShapesEditor", () => {
  function Shapes({ spy, initial = [] }: { spy: (s: CanvasShape[]) => void; initial?: CanvasShape[] }) {
    const [shapes, setShapes] = useState<CanvasShape[]>(initial);
    return wrap(
      <CanvasShapesEditor
        shapes={shapes}
        onChange={(s) => {
          spy(s);
          setShapes(s);
        }}
      />,
    );
  }

  it("adds a shape of the chosen type", async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Shapes spy={spy} />);
    await user.click(screen.getByRole("button", { name: "Add shape" }));
    expect(spy).toHaveBeenLastCalledWith([{ type: "rect", x: 0, y: 0, w: 8, h: 8, fill: "#ff0000" }]);
  });

  it("keeps numbers as numbers and {{…}} expressions as text", () => {
    const spy = vi.fn();
    render(<Shapes spy={spy} initial={[{ type: "rect", x: 0, y: 0, w: 8, h: 8 }]} />);
    fireEvent.change(screen.getByLabelText("X *"), { target: { value: "12" } });
    expect(spy.mock.calls.at(-1)![0][0].x).toBe(12);
    fireEvent.change(screen.getByLabelText("Width *"), { target: { value: "{{weather.temp}}" } });
    expect(spy.mock.calls.at(-1)![0][0].w).toBe("{{weather.temp}}");
    fireEvent.change(screen.getByLabelText("Only if"), { target: { value: "{{weather.temp > 20}}" } });
    expect(spy.mock.calls.at(-1)![0][0].if).toBe("{{weather.temp > 20}}");
  });

  it("reorders and deletes shapes", async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    const a: CanvasShape = { type: "rect", x: 0, y: 0, w: 1, h: 1 };
    const b: CanvasShape = { type: "circle", cx: 1, cy: 1, r: 1 };
    render(<Shapes spy={spy} initial={[a, b]} />);
    await user.click(screen.getByRole("button", { name: "Move shape 2 up" }));
    expect(spy).toHaveBeenLastCalledWith([b, a]);
    await user.click(screen.getByRole("button", { name: "Delete shape 1" }));
    expect(spy).toHaveBeenLastCalledWith([a]);
  });

  it("edits as JSON, reporting invalid JSON without applying it", async () => {
    const user = userEvent.setup();
    const spy = vi.fn();
    render(<Shapes spy={spy} />);
    await user.click(screen.getByRole("switch", { name: "Edit as JSON" }));
    const json = screen.getByLabelText("Shapes JSON");
    fireEvent.change(json, { target: { value: "[{" } });
    expect(screen.getByRole("alert")).toHaveTextContent("Not valid JSON");
    expect(spy).not.toHaveBeenCalled();
    fireEvent.change(json, { target: { value: '{"type": "rect"}' } });
    expect(screen.getByRole("alert")).toHaveTextContent("Shapes JSON must be a list.");
    fireEvent.change(json, {
      target: { value: '[{"type": "line", "x1": 0, "y1": 0, "x2": 3, "y2": 3, "stroke": "red"}]' },
    });
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(spy).toHaveBeenLastCalledWith([{ type: "line", x1: 0, y1: 0, x2: 3, y2: 3, stroke: "red" }]);
  });
});

describe("CanvasSourcePicker", () => {
  it("offers only plugin variables whose format is canvas", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(wrap(<CanvasSourcePicker source={null} onChange={onChange} />));
    await user.click(await screen.findByRole("combobox", { name: "Plugin canvas variable" }));
    const listbox = await screen.findByRole("listbox");
    const options = within(listbox)
      .getAllByRole("option")
      .map((o) => o.textContent);
    expect(options).toEqual(["None", "art.canvas — Scene"]);
    await user.click(within(listbox).getByRole("option", { name: "art.canvas — Scene" }));
    expect(onChange).toHaveBeenLastCalledWith("{{art.canvas}}");
  });

  it("says so when no plugin offers a canvas variable", async () => {
    vi.mocked(api.getTemplateVariables).mockResolvedValue({ ...VARIABLES, variable_metadata: {} });
    render(wrap(<CanvasSourcePicker source={null} onChange={vi.fn()} />));
    await waitFor(() => expect(screen.getByTestId("canvas-source-empty")).toBeInTheDocument());
  });

  it("takes a typed expression", () => {
    const onChange = vi.fn();
    render(wrap(<CanvasSourcePicker source={null} onChange={onChange} />));
    fireEvent.change(screen.getByLabelText("Source expression"), { target: { value: "{{art.canvas}}" } });
    expect(onChange).toHaveBeenLastCalledWith("{{art.canvas}}");
  });
});
