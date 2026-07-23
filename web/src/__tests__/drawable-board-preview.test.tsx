import { fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DrawableBoardPreview } from "@/components/drawable-board-preview";

function makeTile(row: number, col: number): HTMLElement {
  const el = document.createElement("div");
  el.setAttribute("data-row", String(row));
  el.setAttribute("data-col", String(col));
  document.body.appendChild(el);
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
    const tile = makeTile(1, 3);
    document.elementFromPoint = vi.fn().mockReturnValue(tile);

    fireEvent.pointerDown(surface, { button: 0, clientX: 5, clientY: 5, pointerId: 1 });
    expect(onStrokePreview).toHaveBeenCalledWith([{ row: 1, col: 3 }]);
    fireEvent.pointerUp(surface, { pointerId: 1 });
    expect(onStrokeCommit).toHaveBeenCalledWith([{ row: 1, col: 3 }]);
  });

  it("accumulates unique cells across a drag", () => {
    const { surface, onStrokeCommit } = setup();
    const t1 = makeTile(0, 0);
    const t2 = makeTile(0, 1);
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
    document.elementFromPoint = vi.fn().mockReturnValue(makeTile(0, 0));
    fireEvent.pointerDown(surface, { button: 0, pointerId: 1 });
    fireEvent.pointerUp(surface, { pointerId: 1 });
    expect(onStrokePreview).not.toHaveBeenCalled();
    expect(onStrokeCommit).not.toHaveBeenCalled();
  });

  it("clears the stroke without committing on pointercancel", () => {
    const { surface, onStrokePreview, onStrokeCommit } = setup();
    document.elementFromPoint = vi.fn().mockReturnValue(makeTile(0, 0));
    fireEvent.pointerDown(surface, { button: 0, pointerId: 1 });
    fireEvent.pointerCancel(surface, { pointerId: 1 });
    expect(onStrokeCommit).not.toHaveBeenCalled();
    expect(onStrokePreview).toHaveBeenLastCalledWith([]);
  });
});
