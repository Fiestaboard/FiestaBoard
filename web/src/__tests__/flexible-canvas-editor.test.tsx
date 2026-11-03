import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, it, vi } from "vitest";

import { CanvasBlockEditor } from "@/components/flexible-page-editor/canvas-block-editor";
import { type FlexibleBlock } from "@/lib/api";

vi.mock("@/components/canvas-editor/canvas-draw-tab", () => ({
  CanvasDrawTab: () => <div data-testid="paint-pad" />,
}));

it("requires an explicit source size before painting a size-less canvas", () => {
  const onChange = vi.fn();
  render(
    <CanvasBlockEditor
      label="Block 1"
      onChange={onChange}
      block={{
        id: "canvas",
        kind: "canvas",
        canvas: { content: { palette: { r: "#ff0000" }, pixels: Array(16).fill("r".repeat(16)) } },
      }}
    />,
  );
  expect(screen.queryByTestId("paint-pad")).not.toBeInTheDocument();
  expect(screen.getByText(/Choose an explicit canvas size before painting/)).toBeInTheDocument();
  expect(onChange).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Block 1 canvas width"), { target: { value: "16" } });
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.queryByTestId("paint-pad")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Block 1 canvas height"), { target: { value: "16" } });
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({
      canvas: { content: expect.objectContaining({ size: [16, 16], pixels: Array(16).fill("r".repeat(16)) }) },
    }),
  );
});

it("lets an existing canvas dimension be cleared and replaced before committing", async () => {
  function Editor() {
    const [block, setBlock] = useState<FlexibleBlock>({
      id: "canvas",
      kind: "canvas",
      canvas: { content: { size: [8, 8] } },
    });
    return (
      <>
        <CanvasBlockEditor label="Block 1" block={block} onChange={setBlock} />
        <output aria-label="Canvas size">{JSON.stringify(block.canvas?.content?.size)}</output>
      </>
    );
  }
  render(<Editor />);
  const user = userEvent.setup();
  const width = screen.getByLabelText("Block 1 canvas width");
  await user.clear(width);
  expect(width).toHaveValue(null);
  expect(screen.getByLabelText("Canvas size")).toHaveTextContent("[8,8]");
  await user.type(width, "16");
  await user.tab();
  expect(width).toHaveValue(16);
  expect(screen.getByLabelText("Canvas size")).toHaveTextContent("[16,8]");
});
