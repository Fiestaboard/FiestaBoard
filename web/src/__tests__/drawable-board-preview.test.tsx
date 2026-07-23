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
