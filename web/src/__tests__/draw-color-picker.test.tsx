import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DrawColorPickerContent } from "@/components/tiptap-template-editor/components/DrawColorPickerContent";

describe("DrawColorPickerContent", () => {
  it("renders 8 colors plus eraser and reports selection", () => {
    const onSelect = vi.fn();
    render(<DrawColorPickerContent current="red" onSelect={onSelect} />);

    for (const name of ["red", "orange", "yellow", "green", "blue", "violet", "white", "black"]) {
      expect(screen.getByTestId(`draw-color-${name}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("draw-color-red")).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByTestId("draw-color-blue"));
    expect(onSelect).toHaveBeenCalledWith("blue");

    fireEvent.click(screen.getByTestId("draw-color-eraser"));
    expect(onSelect).toHaveBeenCalledWith("eraser");
  });
});
