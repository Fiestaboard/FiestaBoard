/**
 * BB-E-18: a page moved to a smaller board keeps its blank padding rows. They
 * are not lines the board limit applies to, so neither editor's caption may
 * call them over the limit; a row with content past the board still is.
 */
import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PlainTextEditor } from "@/components/plain-text-editor";
import { TipTapTemplateEditor } from "@/components/tiptap-template-editor/TipTapTemplateEditor";

describe("rich editor line caption", () => {
  it("does not count blank padding rows against a smaller board", async () => {
    render(
      <TipTapTemplateEditor
        value={"HELLO\n\n\n\n\n"}
        onChange={vi.fn()}
        showToolbar={false}
        boardLines={3}
        boardWidth={15}
      />,
    );
    await waitFor(() => expect(screen.getByText(/1 \/ 3 lines/)).toBeInTheDocument());
    expect(screen.queryByText(/exceeds/)).not.toBeInTheDocument();
  });

  it("still numbers every row in the gutter, blank ones included", async () => {
    render(
      <TipTapTemplateEditor
        value={"HELLO\n\n\n\n\n"}
        onChange={vi.fn()}
        showToolbar={false}
        boardLines={3}
        boardWidth={15}
      />,
    );
    await waitFor(() => expect(screen.getByText(/1 \/ 3 lines/)).toBeInTheDocument());
    expect(screen.getByText("6", { exact: true })).toBeInTheDocument();
  });

  it("still flags content past the board's last row", async () => {
    render(
      <TipTapTemplateEditor
        value={"A\n\n\n\nE\n"}
        onChange={vi.fn()}
        showToolbar={false}
        boardLines={3}
        boardWidth={15}
      />,
    );
    await waitFor(() => expect(screen.getByText(/5 \/ 3 lines/)).toBeInTheDocument());
    expect(screen.getByText(/exceeds the 3-line board limit/)).toBeInTheDocument();
  });
});

describe("plain editor line caption", () => {
  it("does not count blank padding rows against a smaller board", () => {
    render(<PlainTextEditor value={"HELLO\n\n\n\n\n"} onChange={vi.fn()} boardLines={3} boardWidth={15} />);
    expect(screen.getByText(/1 \/ 3 lines/)).toBeInTheDocument();
    expect(screen.queryByText(/exceeds/)).not.toBeInTheDocument();
  });

  it("still flags content past the board's last row", () => {
    render(<PlainTextEditor value={"A\n\n\n\nE\n"} onChange={vi.fn()} boardLines={3} boardWidth={15} />);
    expect(screen.getByText(/5 \/ 3 lines/)).toBeInTheDocument();
    expect(screen.getByText(/exceeds the 3-line board limit/)).toBeInTheDocument();
  });
});
