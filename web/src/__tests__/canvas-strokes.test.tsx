import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { type PadTool,PixelPad } from "@/components/canvas-editor/canvas-draw-tab";
import type { PixelGrid } from "@/lib/canvas-editing";

function Pad({ tool = "brush", initial }: { tool?: PadTool; initial?: PixelGrid }) {
  const [grid, setGrid] = useState<PixelGrid>(initial ?? Array.from({ length: 4 }, () => Array(4).fill(null)));
  const [picked, setPicked] = useState<string | null>(null);
  return (
    <>
      <PixelPad
        grid={grid}
        tool={tool}
        color="#ff0000"
        zoom={8}
        showGrid={false}
        onChange={setGrid}
        onPick={setPicked}
      />
      <output data-testid="pixels">{JSON.stringify(grid)}</output>
      <output data-testid="picked">{picked}</output>
    </>
  );
}

function point(kind: "pointerDown" | "pointerMove", x: number, y: number) {
  fireEvent[kind](screen.getByTestId("pixel-pad"), { clientX: x * 8 + 1, clientY: y * 8 + 1, pointerId: 1 });
}
const red = "#ff0000";
const blank = [null, null, null, null];
const pixels = () => JSON.parse(screen.getByTestId("pixels").textContent!);

describe("continuous pixel strokes", () => {
  it.each([
    { start: [0, 0], end: [3, 0], expected: [[red, red, red, red], blank, blank, blank] },
    {
      start: [0, 0],
      end: [0, 3],
      expected: [
        [red, null, null, null],
        [red, null, null, null],
        [red, null, null, null],
        [red, null, null, null],
      ],
    },
    {
      start: [3, 3],
      end: [0, 0],
      expected: [
        [red, null, null, null],
        [null, red, null, null],
        [null, null, red, null],
        [null, null, null, red],
      ],
    },
  ])("fills skipped cells from $start to $end", ({ start, end, expected }) => {
    render(<Pad />);
    point("pointerDown", start[0], start[1]);
    point("pointerMove", end[0], end[1]);
    expect(pixels()).toEqual(expected);
  });

  it("erases skipped cells including when the stroke starts on transparency", () => {
    render(<Pad tool="eraser" initial={[[null, red, red, red], blank, blank, blank]} />);
    point("pointerDown", 0, 0);
    point("pointerMove", 3, 0);
    expect(pixels()).toEqual([blank, blank, blank, blank]);
  });

  it.each(["pointerUp", "pointerCancel", "lostPointerCapture", "pointerLeave"] as const)(
    "ends a stroke on %s",
    (event) => {
      render(<Pad />);
      point("pointerDown", 0, 0);
      fireEvent[event](screen.getByTestId("pixel-pad"), { pointerId: 1 });
      point("pointerMove", 3, 0);
      point("pointerDown", 3, 3);
      expect(pixels()).toEqual([[red, null, null, null], blank, blank, [null, null, null, red]]);
    },
  );

  it("breaks interpolation after leaving the grid bounds", () => {
    render(<Pad />);
    point("pointerDown", 0, 0);
    point("pointerMove", -1, 0);
    point("pointerMove", 3, 0);
    expect(pixels()).toEqual([[red, null, null, red], blank, blank, blank]);
  });

  it("fills only the initial region during a drag", () => {
    render(<Pad tool="fill" initial={[[null, null, "#0000ff", null]]} />);
    point("pointerDown", 0, 0);
    point("pointerMove", 3, 0);
    expect(pixels()).toEqual([[red, red, "#0000ff", null]]);
  });

  it("picks only the initial cell during a drag", () => {
    render(<Pad tool="picker" initial={[[red, null, null, "#0000ff"]]} />);
    point("pointerDown", 0, 0);
    point("pointerMove", 3, 0);
    expect(screen.getByTestId("picked")).toHaveTextContent(red);
    expect(pixels()).toEqual([[red, null, null, "#0000ff"]]);
  });
});
