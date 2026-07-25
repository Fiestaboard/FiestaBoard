import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DrawCharPickerContent } from "@/components/tiptap-template-editor/components/DrawCharPickerContent";
import { DRAW_CHARS } from "@/components/tiptap-template-editor/utils/draw-mode";

describe("DrawCharPickerContent", () => {
  it("renders every stampable character and reports selection", () => {
    const onSelect = vi.fn();
    const { container } = render(
      <DrawCharPickerContent current={{ kind: "color", color: "red" }} onSelect={onSelect} />,
    );

    const buttons = container.querySelectorAll("[data-draw-char]");
    expect(buttons).toHaveLength(DRAW_CHARS.length);
    expect(container.querySelector('[data-draw-char="A"]')).toBeTruthy();
    expect(container.querySelector('[data-draw-char="°"]')).toBeTruthy();
    expect(container.querySelector('[data-draw-char=" "]')).toBeNull();

    fireEvent.click(container.querySelector('[data-draw-char="B"]') as HTMLElement);
    expect(onSelect).toHaveBeenCalledWith({ kind: "char", char: "B" });
  });

  it("marks the current character pressed", () => {
    const { container } = render(<DrawCharPickerContent current={{ kind: "char", char: "Z" }} onSelect={vi.fn()} />);
    expect(container.querySelector('[data-draw-char="Z"]')).toHaveAttribute("aria-pressed", "true");
    expect(container.querySelector('[data-draw-char="A"]')).toHaveAttribute("aria-pressed", "false");
  });

  it("keeps exactly one button in the tab order (roving tabindex)", () => {
    const { container } = render(<DrawCharPickerContent current={{ kind: "eraser" }} onSelect={vi.fn()} />);
    const buttons = Array.from(container.querySelectorAll<HTMLButtonElement>("[data-draw-char]"));
    expect(buttons.filter((b) => b.tabIndex === 0)).toHaveLength(1);
    expect(buttons[0].tabIndex).toBe(0);
  });

  it("starts the tab order on the currently selected character", () => {
    const { container } = render(<DrawCharPickerContent current={{ kind: "char", char: "Z" }} onSelect={vi.fn()} />);
    expect(container.querySelector<HTMLButtonElement>('[data-draw-char="Z"]')!.tabIndex).toBe(0);
    expect(container.querySelector<HTMLButtonElement>('[data-draw-char="A"]')!.tabIndex).toBe(-1);
  });

  it("moves focus with arrow keys across the 8-column grid", () => {
    const { container } = render(<DrawCharPickerContent current={{ kind: "eraser" }} onSelect={vi.fn()} />);
    const buttons = Array.from(container.querySelectorAll<HTMLButtonElement>("[data-draw-char]"));

    buttons[0].focus();
    fireEvent.keyDown(buttons[0], { key: "ArrowRight" });
    expect(document.activeElement).toBe(buttons[1]);
    expect(buttons[1].tabIndex).toBe(0);
    expect(buttons[0].tabIndex).toBe(-1);

    fireEvent.keyDown(buttons[1], { key: "ArrowDown" });
    expect(document.activeElement).toBe(buttons[9]);

    fireEvent.keyDown(buttons[9], { key: "ArrowUp" });
    expect(document.activeElement).toBe(buttons[1]);

    fireEvent.keyDown(buttons[1], { key: "ArrowLeft" });
    expect(document.activeElement).toBe(buttons[0]);
  });

  it("wraps focus at the grid edges and supports Home/End", () => {
    const { container } = render(<DrawCharPickerContent current={{ kind: "eraser" }} onSelect={vi.fn()} />);
    const buttons = Array.from(container.querySelectorAll<HTMLButtonElement>("[data-draw-char]"));
    const last = buttons.length - 1;

    buttons[0].focus();
    fireEvent.keyDown(buttons[0], { key: "ArrowLeft" });
    expect(document.activeElement).toBe(buttons[last]);

    fireEvent.keyDown(buttons[last], { key: "ArrowRight" });
    expect(document.activeElement).toBe(buttons[0]);

    fireEvent.keyDown(buttons[0], { key: "End" });
    expect(document.activeElement).toBe(buttons[last]);

    fireEvent.keyDown(buttons[last], { key: "Home" });
    expect(document.activeElement).toBe(buttons[0]);
  });

  it("keeps an explicit width on the wrapper so the dropdown panel cannot shrink-fit", () => {
    // Regression pin: the ToolbarDropdown panel is absolutely positioned in a
    // trigger-sized wrapper; without an explicit width the panel collapses to
    // ~36px and the grid-cols-8 (minmax(0,1fr)) tracks overlap the buttons.
    // jsdom can't measure layout, so pin the class itself.
    render(<DrawCharPickerContent current={{ kind: "eraser" }} onSelect={vi.fn()} />);
    expect(screen.getByTestId("draw-char-picker")).toHaveClass("w-64");
  });
});
