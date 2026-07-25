import { fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DrawableBoardPreview } from "@/components/drawable-board-preview";

// `container` defaults to document.body, which is OUTSIDE the rendered
// DrawableBoardPreview wrapper — useful for asserting that hits outside the
// draw surface are rejected. Tests that want a hit-testable tile must pass
// the `surface` element returned by `setup()` so the tile lands inside the
// wrapper the containment check walks.
function makeTile(row: number, col: number, container: HTMLElement = document.body): HTMLElement {
  const el = document.createElement("div");
  el.setAttribute("data-row", String(row));
  el.setAttribute("data-col", String(col));
  container.appendChild(el);
  return el;
}

describe("DrawableBoardPreview", () => {
  beforeEach(() => {
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", () => {});
    // jsdom lacks pointer capture
    Element.prototype.setPointerCapture = Element.prototype.setPointerCapture || (() => {});
    Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture || (() => {});
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  function setup(active = true) {
    const onStrokePreview = vi.fn();
    const onStrokeCommit = vi.fn();
    const utils = render(
      <DrawableBoardPreview active={active} onStrokePreview={onStrokePreview} onStrokeCommit={onStrokeCommit}>
        <div data-testid="board" />
      </DrawableBoardPreview>,
    );
    const surface = utils.getByTestId("board").parentElement as HTMLElement;
    return { surface, onStrokePreview, onStrokeCommit };
  }

  it("commits a single-cell stroke on click", () => {
    const { surface, onStrokePreview, onStrokeCommit } = setup();
    const tile = makeTile(1, 3, surface);
    document.elementFromPoint = vi.fn().mockReturnValue(tile);

    fireEvent.pointerDown(surface, { button: 0, clientX: 5, clientY: 5, pointerId: 1 });
    expect(onStrokePreview).toHaveBeenCalledWith([{ row: 1, col: 3 }]);
    fireEvent.pointerUp(surface, { pointerId: 1 });
    expect(onStrokeCommit).toHaveBeenCalledWith([{ row: 1, col: 3 }]);
  });

  it("accumulates unique cells across a drag", () => {
    const { surface, onStrokeCommit } = setup();
    const t1 = makeTile(0, 0, surface);
    const t2 = makeTile(0, 1, surface);
    const efp = vi.fn().mockReturnValueOnce(t1).mockReturnValueOnce(t2).mockReturnValue(t2);
    document.elementFromPoint = efp;

    fireEvent.pointerDown(surface, { button: 0, pointerId: 1 });
    fireEvent.pointerMove(surface, { pointerId: 1 });
    fireEvent.pointerMove(surface, { pointerId: 1 }); // same tile again — deduped
    fireEvent.pointerUp(surface, { pointerId: 1 });

    expect(onStrokeCommit).toHaveBeenCalledWith([
      { row: 0, col: 0 },
      { row: 0, col: 1 },
    ]);
    expect(onStrokeCommit).toHaveBeenCalledTimes(1);
  });

  it("does nothing when inactive", () => {
    const { surface, onStrokePreview, onStrokeCommit } = setup(false);
    document.elementFromPoint = vi.fn().mockReturnValue(makeTile(0, 0, surface));
    fireEvent.pointerDown(surface, { button: 0, pointerId: 1 });
    fireEvent.pointerUp(surface, { pointerId: 1 });
    expect(onStrokePreview).not.toHaveBeenCalled();
    expect(onStrokeCommit).not.toHaveBeenCalled();
  });

  it("coalesces multiple new cells into one rAF preview flush", () => {
    let frame: FrameRequestCallback | null = null;
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      frame = cb;
      return 1;
    });
    const { surface, onStrokePreview } = setup();
    const t1 = makeTile(0, 0, surface);
    const t2 = makeTile(0, 1, surface);
    document.elementFromPoint = vi.fn().mockReturnValueOnce(t1).mockReturnValue(t2);

    fireEvent.pointerDown(surface, { button: 0, pointerId: 1 });
    fireEvent.pointerMove(surface, { pointerId: 1 });
    expect(onStrokePreview).not.toHaveBeenCalled();

    frame!(0);
    expect(onStrokePreview).toHaveBeenCalledTimes(1);
    expect(onStrokePreview).toHaveBeenCalledWith([
      { row: 0, col: 0 },
      { row: 0, col: 1 },
    ]);
  });

  it("aborts the stroke when deactivated mid-stroke", () => {
    const onStrokePreview = vi.fn();
    const onStrokeCommit = vi.fn();
    const utils = render(
      <DrawableBoardPreview active onStrokePreview={onStrokePreview} onStrokeCommit={onStrokeCommit}>
        <div data-testid="board" />
      </DrawableBoardPreview>,
    );
    const surface = utils.getByTestId("board").parentElement as HTMLElement;
    document.elementFromPoint = vi.fn().mockReturnValue(makeTile(0, 0, surface));

    fireEvent.pointerDown(surface, { button: 0, pointerId: 1 });
    utils.rerender(
      <DrawableBoardPreview active={false} onStrokePreview={onStrokePreview} onStrokeCommit={onStrokeCommit}>
        <div data-testid="board" />
      </DrawableBoardPreview>,
    );

    expect(onStrokePreview).toHaveBeenLastCalledWith([]);
    fireEvent.pointerUp(surface, { pointerId: 1 });
    expect(onStrokeCommit).not.toHaveBeenCalled();
  });

  it("clears the stroke without committing on pointercancel", () => {
    const { surface, onStrokePreview, onStrokeCommit } = setup();
    document.elementFromPoint = vi.fn().mockReturnValue(makeTile(0, 0, surface));
    fireEvent.pointerDown(surface, { button: 0, pointerId: 1 });
    fireEvent.pointerCancel(surface, { pointerId: 1 });
    expect(onStrokeCommit).not.toHaveBeenCalled();
    expect(onStrokePreview).toHaveBeenLastCalledWith([]);
  });

  it("clears preview state before committing (self-cleaning on commit)", () => {
    const order: string[] = [];
    const onStrokePreview = vi.fn((cells) => order.push(`preview:${JSON.stringify(cells)}`));
    const onStrokeCommit = vi.fn((cells) => order.push(`commit:${JSON.stringify(cells)}`));
    const utils = render(
      <DrawableBoardPreview active onStrokePreview={onStrokePreview} onStrokeCommit={onStrokeCommit}>
        <div data-testid="board" />
      </DrawableBoardPreview>,
    );
    const surface = utils.getByTestId("board").parentElement as HTMLElement;
    const tile = makeTile(4, 2, surface);
    document.elementFromPoint = vi.fn().mockReturnValue(tile);

    fireEvent.pointerDown(surface, { button: 0, pointerId: 1 });
    expect(onStrokePreview).toHaveBeenLastCalledWith([{ row: 4, col: 2 }]);

    fireEvent.pointerUp(surface, { pointerId: 1 });

    // onStrokePreview must be cleared before onStrokeCommit fires, so a
    // consumer that forgets to clear its own preview state never ends up
    // with a stuck ghost stroke.
    expect(onStrokePreview).toHaveBeenLastCalledWith([]);
    expect(onStrokeCommit).toHaveBeenCalledWith([{ row: 4, col: 2 }]);
    expect(order).toEqual([
      `preview:${JSON.stringify([{ row: 4, col: 2 }])}`,
      "preview:[]",
      `commit:${JSON.stringify([{ row: 4, col: 2 }])}`,
    ]);
  });

  it("ignores a second concurrent pointer mid-stroke (down, move, and up)", () => {
    const { surface, onStrokePreview, onStrokeCommit } = setup();
    const t1 = makeTile(0, 0, surface);
    const t2 = makeTile(0, 1, surface);
    const intruderTile = makeTile(3, 3, surface);
    // Key hit-testing off coordinates rather than call order so the mock
    // stays valid no matter which handlers consult elementFromPoint.
    const byPoint: Record<string, HTMLElement> = { "5,5": t1, "6,6": t2, "50,50": intruderTile };
    document.elementFromPoint = vi.fn((x: number, y: number) => byPoint[`${x},${y}`] ?? null);

    // Pointer 1 starts a stroke.
    fireEvent.pointerDown(surface, { button: 0, pointerId: 1, clientX: 5, clientY: 5 });
    expect(onStrokePreview).toHaveBeenLastCalledWith([{ row: 0, col: 0 }]);

    // A second pointer lands mid-stroke on a different tile: its down must
    // not restart the stroke, its moves must not extend it, and its up must
    // not commit it.
    fireEvent.pointerDown(surface, { button: 0, pointerId: 2, clientX: 50, clientY: 50 });
    fireEvent.pointerMove(surface, { pointerId: 2, clientX: 50, clientY: 50 });
    fireEvent.pointerUp(surface, { pointerId: 2, clientX: 50, clientY: 50 });
    expect(onStrokeCommit).not.toHaveBeenCalled();

    // Pointer 1 is still drawing and finishes its stroke normally.
    fireEvent.pointerMove(surface, { pointerId: 1, clientX: 6, clientY: 6 });
    fireEvent.pointerUp(surface, { pointerId: 1, clientX: 6, clientY: 6 });

    expect(onStrokeCommit).toHaveBeenCalledTimes(1);
    expect(onStrokeCommit).toHaveBeenCalledWith([
      { row: 0, col: 0 },
      { row: 0, col: 1 },
    ]);
    // The intruder's cell never leaked into any preview flush either.
    for (const call of onStrokePreview.mock.calls) {
      expect(call[0]).not.toContainEqual({ row: 3, col: 3 });
    }
  });

  it("ignores hits on tiles outside the draw surface (e.g. another board preview elsewhere on the page)", () => {
    const { surface, onStrokePreview, onStrokeCommit } = setup();
    // Deliberately NOT passed `surface` — this tile lives in document.body,
    // simulating a tile from an unrelated board preview (e.g. the AI chat
    // drawer's inline previews) that also carries data-row/data-col.
    const outsideTile = makeTile(2, 2);
    document.elementFromPoint = vi.fn().mockReturnValue(outsideTile);

    fireEvent.pointerDown(surface, { button: 0, pointerId: 1, clientX: 5, clientY: 5 });
    fireEvent.pointerMove(surface, { pointerId: 1, clientX: 6, clientY: 6 });
    fireEvent.pointerUp(surface, { pointerId: 1 });

    expect(onStrokePreview).not.toHaveBeenCalled();
    expect(onStrokeCommit).not.toHaveBeenCalled();
  });
});
