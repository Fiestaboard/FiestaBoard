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
});
