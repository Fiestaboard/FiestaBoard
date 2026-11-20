/**
 * The rich template behaves like a text field (bug bash E2, desktop editor
 * audit root problem 5): BB-E-1 multi-line paste, BB-E-14 copy without the
 * caret anchors, BB-E-15 Esc from a picker keeps the caret, BB-E-16 a focus
 * ring, BB-E-8 rows stay on one line inside the card, BB-E-24 Undo starts
 * disabled.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
        formatting: { bold: {} },
      }),
    },
  };
});

type Props = ComponentProps<typeof TipTapTemplateEditor>;

function renderEditor(props: Partial<Props> = {}) {
  const onChange = vi.fn();
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const all: Props = { value: "\n\n\n\n\n", onChange, showToolbar: false, boardLines: 6, boardWidth: 22, ...props };
  const view = render(
    <QueryClientProvider client={client}>
      <TipTapTemplateEditor {...all} />
    </QueryClientProvider>,
  );
  const rerender = (next: Partial<Props>) =>
    view.rerender(
      <QueryClientProvider client={client}>
        <TipTapTemplateEditor {...all} {...next} />
      </QueryClientProvider>,
    );
  return { ...view, onChange, rerender };
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

function clipboard(data: Record<string, string>) {
  const store = { ...data };
  return {
    getData: (type: string) => store[type] ?? "",
    setData: (type: string, value: string) => {
      store[type] = value;
    },
    clearData: () => {
      for (const key of Object.keys(store)) delete store[key];
    },
    types: Object.keys(store),
    files: [],
    items: [],
    store,
  };
}

function paste(target: Element, data: Record<string, string>) {
  const event = new Event("paste", { bubbles: true, cancelable: true });
  Object.defineProperty(event, "clipboardData", { value: clipboard(data) });
  fireEvent(target, event);
}

const lastLines = (onChange: ReturnType<typeof vi.fn>) =>
  (onChange.mock.calls.at(-1)?.[0] as string | undefined)?.split("\n") ?? [];

describe("pasting text from outside the app (BB-E-1)", () => {
  it("keeps every line of plain multi-line text, one per row", async () => {
    const { onChange } = renderEditor();
    const editor = await editorOf();
    act(() => {
      editor.commands.focus("start");
    });
    paste(editor.view.dom, { "text/plain": "first\nsecond\r\nthird" });
    await waitFor(() => expect(lastLines(onChange).slice(0, 3)).toEqual(["FIRST", "SECOND", "THIRD"]));
  });

  it("keeps every line of a rich (HTML) paste from a document", async () => {
    const { onChange } = renderEditor();
    const editor = await editorOf();
    act(() => {
      editor.commands.focus("start");
    });
    paste(editor.view.dom, {
      "text/plain": "Big Title\nline one\nline two",
      "text/html": "<h1>Big Title</h1><ul><li>line one</li><li>line two</li></ul>",
    });
    await waitFor(() => expect(lastLines(onChange).slice(0, 3)).toEqual(["BIG TITLE", "LINE ONE", "LINE TWO"]));
  });

  it("still turns a pasted template's markup into its chips across lines", async () => {
    const { onChange } = renderEditor();
    const editor = await editorOf();
    act(() => {
      editor.commands.focus("start");
    });
    paste(editor.view.dom, { "text/plain": "TEMP {{weather.temp}}\n{{red}} HOT" });
    await waitFor(() => expect(lastLines(onChange).slice(0, 2)).toEqual(["TEMP {{weather.temp}}", "{{red}} HOT"]));
  });
});

describe("copying from the template (BB-E-14)", () => {
  it("puts the template text on the clipboard without zero-width caret anchors", async () => {
    renderEditor({ value: "\n    GOOD MORNING\n\n\n\n" });
    const editor = await editorOf();
    await waitFor(() => expect(editor.getText()).toContain("GOOD MORNING"));
    act(() => {
      editor.commands.selectAll();
    });
    const event = new Event("copy", { bubbles: true, cancelable: true });
    const data = clipboard({});
    Object.defineProperty(event, "clipboardData", { value: data });
    fireEvent(editor.view.dom, event);
    const text = data.store["text/plain"];
    expect(text).toContain("GOOD MORNING");
    expect(text).not.toMatch(/​/);
  });
});

describe("Esc from a toolbar picker (BB-E-15)", () => {
  it("closes the picker and puts the caret back in the template", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      renderEditor({ showToolbar: true, value: "HELLO\n\n\n\n\n" });
      const editor = await editorOf();
      act(() => {
        editor.commands.focus(3);
      });
      const colors = await screen.findByRole("button", { name: "Colors" });
      fireEvent.click(colors);
      colors.focus();
      expect(document.activeElement).toBe(colors);
      fireEvent.keyDown(colors, { key: "Escape" });
      await act(async () => {
        vi.advanceTimersByTime(50);
      });
      await waitFor(() => expect(editor.view.hasFocus() || document.activeElement === editor.view.dom).toBe(true));
      expect(editor.state.selection.from).toBe(3);
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("the template card (BB-E-16, BB-E-8)", () => {
  it("shows a focus ring on the card while the template has focus", async () => {
    renderEditor();
    await editorOf();
    const card = document.querySelector('[data-slot="template-card"]');
    expect(card).not.toBeNull();
    expect(card!.className).toMatch(/focus-within:ring-\[3px\]/);
    expect(card!.className).toMatch(/focus-within:border-ring/);
  });

  it("keeps a long row inside the card, scrolling instead of spilling", async () => {
    renderEditor();
    await editorOf();
    const scroller = document.querySelector('[data-slot="template-rows"]');
    expect(scroller).not.toBeNull();
    expect(scroller!.className).toMatch(/overflow-x-auto/);
  });

  it("never wraps a row of tiles: chip renderers inherit no-wrap", async () => {
    renderEditor();
    await editorOf();
    const css = [...document.querySelectorAll("style")].map((s) => s.textContent ?? "").join("\n");
    expect(css).toMatch(/\.ProseMirror \.react-renderer\s*\{[^}]*white-space:\s*nowrap/);
  });
});

describe("Undo on an untouched page (BB-E-24)", () => {
  it("is disabled after the page fills the template in, until the user edits", async () => {
    const { rerender } = renderEditor({ showToolbar: true, value: "" });
    const editor = await editorOf();
    rerender({ value: "\n\n\n\n\n" });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });
    expect(editor.can().undo()).toBe(false);
    expect(screen.getByRole("button", { name: "Undo" })).toBeDisabled();
  });
});
