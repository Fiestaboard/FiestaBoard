/**
 * The template card (editor UX pass, FP-4): the card header carries the line
 * count and a caret readout that follows the selection (UX-3-2), rows past
 * the board are tinted and counted (UX-3-4), ⌘E inserts a formula (UX-9-1),
 * and the toolbar's tooltips name their shortcuts (UX-2-3) and call the T
 * menu "Spacing" (UX-2-4).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Editor } from "@tiptap/react";
import type { ComponentProps } from "react";
import { describe, expect, it, vi } from "vitest";

import { TipTapTemplateEditor } from "@/components/tiptap-template-editor/TipTapTemplateEditor";

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = (await importOriginal()) as Record<string, unknown>;
  return {
    ...mod,
    api: {
      ...(mod.api as Record<string, unknown>),
      getTemplateVariables: vi.fn().mockResolvedValue({
        variables: { weather: ["temp"] },
        colors: { red: 63 },
        formatting: { fill_space: { syntax: "{{fill_space}}" } },
      }),
    },
  };
});

type Props = ComponentProps<typeof TipTapTemplateEditor>;

function renderEditor(props: Partial<Props> = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const all: Props = {
    value: "HELLO\nWORLD\n\n\n\n",
    onChange: vi.fn(),
    showToolbar: false,
    boardLines: 6,
    boardWidth: 22,
    ...props,
  };
  return render(
    <QueryClientProvider client={client}>
      <TipTapTemplateEditor {...all} />
    </QueryClientProvider>,
  );
}

async function editorOf(): Promise<Editor> {
  let editor: Editor | undefined;
  await waitFor(() => {
    const dom = document.querySelector(".ProseMirror") as (HTMLElement & { editor?: Editor }) | null;
    editor = dom?.editor;
    expect(editor).toBeDefined();
  });
  return editor!;
}

const meta = () => screen.getByTestId("template-card-meta");

describe("the stretched card (UX-3-1, FP-4b)", () => {
  it("puts the caret at the end on a click in the empty space under the last row", async () => {
    renderEditor({ value: "HELLO\nWORLD" });
    const editor = await editorOf();
    act(() => {
      editor.commands.setTextSelection(1);
    });
    const area = document.querySelector<HTMLElement>('[data-slot="template-rows-area"]')!;
    // jsdom lays nothing out: the rows end at y 0, so any y > 0 is under them.
    fireEvent.mouseDown(area, { button: 0, clientY: 40 });
    expect(editor.state.selection.from).toBe(editor.state.doc.content.size - 1);
    await waitFor(() => expect(editor.isFocused).toBe(true));
  });

  it("leaves a click on a row to the editor", async () => {
    renderEditor({ value: "HELLO\nWORLD" });
    const editor = await editorOf();
    act(() => {
      editor.commands.setTextSelection(1);
    });
    fireEvent.mouseDown(document.querySelector(".ProseMirror")!, { button: 0, clientY: 40 });
    expect(editor.state.selection.from).toBe(1);
  });
});

describe("template card header", () => {
  it("reads the count first and the caret second, inside the card, with no caption", async () => {
    renderEditor({ cardTitle: <span>Template</span> });
    await editorOf();
    const header = document.querySelector('[data-slot="template-card-header"]')!;
    expect(header.closest('[data-slot="template-card"]')).not.toBeNull();
    expect(header).toHaveTextContent("Template");
    expect(meta()).toHaveTextContent("2 / 6 lines · Ln 1, Col 1");
    // The old caption under the card is gone: the count is said once.
    expect(screen.getAllByText(/\/ 6 lines/)).toHaveLength(1);
  });

  it("follows the caret, counting an atom as one column", async () => {
    renderEditor({ value: "HELLO\nA{{red}}BC\n\n\n\n" });
    const editor = await editorOf();
    act(() => {
      editor.commands.focus("end");
    });
    // The end of the document is the last (blank) row.
    await waitFor(() => expect(meta()).toHaveTextContent("Ln 6, Col 1"));
    // Row 2 is "A", a colour tile, "B", "C": the caret after "C" is column 5.
    let end = 0;
    editor.state.doc.descendants((node, pos) => {
      if (node.isText && node.text?.includes("BC")) end = pos + node.text.indexOf("BC") + 2;
    });
    act(() => {
      editor.commands.setTextSelection(end);
    });
    await waitFor(() => expect(meta()).toHaveTextContent("Ln 2, Col 5"));
  });

  it("tints and counts a row made past the board by Enter on the last row (UX-3-4)", async () => {
    renderEditor({ value: "A\nB\nC\nD\nE\nF" });
    const editor = await editorOf();
    expect(screen.queryByTestId("template-rows-past-board")).toBeNull();
    expect(screen.queryByTestId("template-overflow-rows")).toBeNull();
    act(() => {
      editor.commands.focus("end");
    });
    fireEvent.keyDown(editor.view.dom, { key: "Enter" });
    await waitFor(() => expect(screen.getByTestId("template-rows-past-board")).toHaveTextContent("7 > 6 rows"));
    expect(meta()).toHaveTextContent("6 / 6 lines · 7 > 6 rows · Ln 7, Col 1");
    expect(screen.getByTestId("template-overflow-rows")).toBeInTheDocument();
    expect(document.querySelectorAll("[data-past-board]")).toHaveLength(1);
  });
});

describe("Insert a formula (Mod+E)", () => {
  // binding: insertFormula
  it("inserts an empty formula chip at the caret that opens its editor", async () => {
    renderEditor();
    const editor = await editorOf();
    act(() => {
      editor.commands.focus("start");
    });
    const event = fireEvent.keyDown(editor.view.dom, { key: "e", ctrlKey: true });
    expect(event).toBe(false);
    let formula: { expression: string; autoOpen: boolean } | null = null;
    editor.state.doc.descendants((node) => {
      if (node.type.name === "formula") formula = node.attrs as { expression: string; autoOpen: boolean };
    });
    expect(formula).toMatchObject({ expression: "" });
  });

  it("leaves a plain e to typing", async () => {
    renderEditor();
    const editor = await editorOf();
    act(() => {
      editor.commands.focus("start");
    });
    fireEvent.keyDown(editor.view.dom, { key: "e" });
    let formulas = 0;
    editor.state.doc.descendants((node) => {
      if (node.type.name === "formula") formulas++;
    });
    expect(formulas).toBe(0);
  });
});

describe("toolbar labels", () => {
  it("names each shortcut in the tooltip and keeps the accessible names plain (UX-2-3)", async () => {
    const user = userEvent.setup();
    renderEditor({ showToolbar: true });
    await editorOf();
    const undo = await screen.findByRole("button", { name: "Undo" });
    expect(undo).toBeInTheDocument();
    await user.hover(screen.getByRole("button", { name: /Insert formula/ }));
    expect(await screen.findByText(/^Insert formula \((⌘E|Ctrl\+E)\)$/, {}, { timeout: 3000 })).toBeInTheDocument();
  });

  it('calls the T menu "Spacing", not "Formatting" (UX-2-4)', async () => {
    renderEditor({ showToolbar: true });
    await editorOf();
    expect(await screen.findByRole("button", { name: "Spacing" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Formatting" })).toBeNull();
  });
});
