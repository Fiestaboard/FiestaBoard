import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AiDrawerResizeHandle } from "@/components/ai-drawer-resize-handle";
import { MAX_AI_DRAWER_WIDTH, MIN_AI_DRAWER_WIDTH } from "@/lib/ai-drawer-width";

const MAX = 576; // 40% of a 1440px viewport

function setup(overrides: Partial<React.ComponentProps<typeof AiDrawerResizeHandle>> = {}) {
  const onResize = vi.fn();
  const onToggle = vi.fn();
  const onReset = vi.fn();
  render(
    <AiDrawerResizeHandle
      width={400}
      minWidth={MIN_AI_DRAWER_WIDTH}
      maxWidth={MAX}
      onResize={onResize}
      onToggle={onToggle}
      onReset={onReset}
      {...overrides}
    />,
  );
  return { handle: screen.getByRole("separator"), onResize, onToggle, onReset };
}

describe("AiDrawerResizeHandle", () => {
  it("publishes the current width on the separator for assistive tech", () => {
    const { handle } = setup();
    expect(handle).toHaveAttribute("aria-orientation", "vertical");
    expect(handle).toHaveAttribute("aria-valuenow", "400");
    expect(handle).toHaveAttribute("aria-valuemin", String(MIN_AI_DRAWER_WIDTH));
    expect(handle).toHaveAttribute("aria-valuemax", String(MAX));
    expect(handle).toHaveAccessibleName(/resize fiestabot panel/i);
  });

  it("is reachable by keyboard in tab order", async () => {
    const user = userEvent.setup();
    const { handle } = setup();
    await user.tab();
    expect(handle).toHaveFocus();
  });

  // -- keyboard -----------------------------------------------------------

  it("Left arrow widens the drawer by 16px", () => {
    const { handle, onResize } = setup();
    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(onResize).toHaveBeenCalledWith(416);
  });

  it("Right arrow narrows the drawer by 16px", () => {
    const { handle, onResize } = setup();
    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(onResize).toHaveBeenCalledWith(384);
  });

  it("Shift+Left widens by 64px", () => {
    const { handle, onResize } = setup();
    fireEvent.keyDown(handle, { key: "ArrowLeft", shiftKey: true });
    expect(onResize).toHaveBeenCalledWith(464);
  });

  it("Shift+Right narrows by 64px", () => {
    const { handle, onResize } = setup();
    fireEvent.keyDown(handle, { key: "ArrowRight", shiftKey: true });
    expect(onResize).toHaveBeenCalledWith(336);
  });

  it("Home jumps to the narrowest width", () => {
    const { handle, onResize } = setup();
    fireEvent.keyDown(handle, { key: "Home" });
    expect(onResize).toHaveBeenCalledWith(MIN_AI_DRAWER_WIDTH);
  });

  it("End jumps to the widest width this viewport allows", () => {
    const { handle, onResize } = setup();
    fireEvent.keyDown(handle, { key: "End" });
    expect(onResize).toHaveBeenCalledWith(MAX);
  });

  it("Enter toggles between the default and the last custom width", () => {
    const { handle, onToggle } = setup();
    fireEvent.keyDown(handle, { key: "Enter" });
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("Space toggles too", () => {
    const { handle, onToggle } = setup();
    fireEvent.keyDown(handle, { key: " " });
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("leaves other keys to the page", () => {
    const { handle, onResize, onToggle } = setup();
    fireEvent.keyDown(handle, { key: "a" });
    fireEvent.keyDown(handle, { key: "ArrowUp" });
    expect(onResize).not.toHaveBeenCalled();
    expect(onToggle).not.toHaveBeenCalled();
  });

  // -- pointer ------------------------------------------------------------

  it("dragging the handle left widens the drawer by the distance moved", () => {
    const { handle, onResize } = setup();
    fireEvent.pointerDown(handle, { clientX: 1000, pointerId: 1 });
    fireEvent.pointerMove(window, { clientX: 900, pointerId: 1 });
    expect(onResize).toHaveBeenLastCalledWith(500);
  });

  it("dragging right narrows it", () => {
    const { handle, onResize } = setup();
    fireEvent.pointerDown(handle, { clientX: 1000, pointerId: 1 });
    fireEvent.pointerMove(window, { clientX: 1040, pointerId: 1 });
    expect(onResize).toHaveBeenLastCalledWith(360);
  });

  it("keeps resizing from the width it started at, not the last event", () => {
    const { handle, onResize } = setup();
    fireEvent.pointerDown(handle, { clientX: 1000, pointerId: 1 });
    fireEvent.pointerMove(window, { clientX: 950, pointerId: 1 });
    fireEvent.pointerMove(window, { clientX: 900, pointerId: 1 });
    expect(onResize).toHaveBeenNthCalledWith(1, 450);
    expect(onResize).toHaveBeenNthCalledWith(2, 500);
  });

  it("stops resizing once the pointer is released", () => {
    const { handle, onResize } = setup();
    fireEvent.pointerDown(handle, { clientX: 1000, pointerId: 1 });
    fireEvent.pointerUp(window, { clientX: 1000, pointerId: 1 });
    onResize.mockClear();
    fireEvent.pointerMove(window, { clientX: 800, pointerId: 1 });
    expect(onResize).not.toHaveBeenCalled();
  });

  it("marks itself as being dragged so the page can suspend its transition", () => {
    const { handle } = setup();
    fireEvent.pointerDown(handle, { clientX: 1000, pointerId: 1 });
    expect(handle).toHaveAttribute("data-dragging", "true");
    fireEvent.pointerUp(window, { clientX: 1000, pointerId: 1 });
    expect(handle).not.toHaveAttribute("data-dragging", "true");
  });

  it("double-click resets to the default width", () => {
    const { handle, onReset } = setup();
    fireEvent.doubleClick(handle);
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("reports the ceiling as the widest allowed, not the absolute maximum", () => {
    const { handle } = setup({ maxWidth: MAX_AI_DRAWER_WIDTH });
    expect(handle).toHaveAttribute("aria-valuemax", String(MAX_AI_DRAWER_WIDTH));
  });
});
