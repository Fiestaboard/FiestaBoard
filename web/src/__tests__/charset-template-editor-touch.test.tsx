import { resolveCharacterSet } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { TiptapEditorHTMLElement } from "@tiptap/core";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CharsetTemplateEditor } from "@/components/charset-template-editor";

function mediaAt(initialWidth: number, coarse = false) {
  let width = initialWidth;
  const listeners = new Set<() => void>();
  vi.stubGlobal("matchMedia", (query: string) => ({
    get matches() {
      if (query.includes("max-width: 767px")) return width < 768 || coarse;
      if (query.includes("max-width: 639px")) return width < 640;
      if (query === "(pointer: coarse)") return coarse;
      return false;
    },
    media: query,
    addEventListener: (_: string, listener: () => void) => listeners.add(listener),
    removeEventListener: (_: string, listener: () => void) => listeners.delete(listener),
  }));
  return (next: number) =>
    act(() => {
      width = next;
      listeners.forEach((listener) => listener());
    });
}

function mountEditor() {
  const onChange = vi.fn();
  const align = vi.fn();
  const wrap = vi.fn();
  function Harness() {
    const [value, setValue] = useState("First\nSecond");
    return (
      <>
        <CharsetTemplateEditor
          charset={resolveCharacterSet("led_3x5")}
          value={value}
          onChange={(next) => {
            onChange(next);
            setValue(next);
          }}
          boardWidth={16}
          boardLines={3}
          lineAlignments={["left", "right", "center"]}
          lineWrapEnabled={[false, true, false]}
          onLineAlignmentChange={align}
          onLineWrapChange={wrap}
          moreContent={<span>Mirror host switch</span>}
        />
        <output data-testid="value">{value}</output>
      </>
    );
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const result = render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  return { ...result, onChange, align, wrap };
}

afterEach(() => vi.unstubAllGlobals());

describe("CharsetTemplateEditor exact LED picker boundary", () => {
  it("keeps the kit's phone touch sheet at 639px", async () => {
    mediaAt(639);
    const user = userEvent.setup();
    mountEditor();
    await screen.findByRole("textbox", { name: "Template editor" });
    await user.click(screen.getByRole("button", { name: "Text color" }));
    expect(document.querySelector('[data-slot="sheet-content"]')).toBeInTheDocument();
  });

  it.each([
    [640, false],
    [1024, true],
  ] as const)("uses anchored LED tools at %ipx (coarse=%s)", async (width, coarse) => {
    mediaAt(width, coarse);
    const user = userEvent.setup();
    mountEditor();
    await screen.findByRole("textbox", { name: "Template editor" });
    await waitFor(() =>
      expect(document.querySelector('[data-slot="charset-editor-host"]')).toHaveAttribute("data-toolbar", "tablet"),
    );
    expect(document.querySelectorAll('[data-slot="editor-toolbar"]')).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Text color" }));
    expect(screen.getByRole("group", { name: "Text colour" })).toBeVisible();
    expect(document.querySelector('[data-slot="sheet-content"]')).toBeNull();
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "More" }));
    expect(screen.getByText("Mirror host switch")).toBeVisible();
    expect(document.querySelector('[data-slot="sheet-content"]')).toBeNull();
  });

  it("keeps LED markup, editor identity and undo history when crossing 640px", async () => {
    const resize = mediaAt(640);
    const user = userEvent.setup();
    const { onChange } = mountEditor();
    const surface = await screen.findByRole("textbox", { name: "Template editor" });
    const editor = (surface as TiptapEditorHTMLElement).editor!;
    await waitFor(() =>
      expect(document.querySelector('[data-slot="charset-editor-host"]')).toHaveAttribute("data-toolbar", "tablet"),
    );
    act(() => editor.commands.setTextSelection(1));
    await user.click(screen.getByRole("button", { name: "Icon" }));
    fireEvent.click(document.querySelector('[data-icon="sun"]')!);
    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("{{icon:sun}}"));
    expect(onChange).toHaveBeenCalledWith(expect.stringContaining("{{icon:sun}}"));
    resize(639);
    expect(screen.getByRole("textbox", { name: "Template editor" })).toBe(surface);
    expect((surface as TiptapEditorHTMLElement).editor).toBe(editor);
    resize(640);
    await waitFor(() =>
      expect(document.querySelector('[data-slot="charset-editor-host"]')).toHaveAttribute("data-toolbar", "tablet"),
    );
    expect((surface as TiptapEditorHTMLElement).editor).toBe(editor);
    await user.click(screen.getByRole("button", { name: "More" }));
    await user.click(screen.getByRole("button", { name: "Undo" }));
    await waitFor(() => expect(screen.getByTestId("value")).not.toHaveTextContent("{{icon:sun}}"));
    expect(screen.getByTestId("value")).toHaveTextContent("First");
  });

  it("round-trips a selected LED text color through the retained kit serializer", async () => {
    mediaAt(640);
    const user = userEvent.setup();
    const { onChange } = mountEditor();
    const surface = await screen.findByRole("textbox", { name: "Template editor" });
    const editor = (surface as TiptapEditorHTMLElement).editor!;
    await waitFor(() =>
      expect(document.querySelector('[data-slot="charset-editor-host"]')).toHaveAttribute("data-toolbar", "tablet"),
    );
    act(() => editor.commands.setTextSelection({ from: 2, to: 7 }));
    await user.click(screen.getByRole("button", { name: "Text color" }));
    fireEvent.click(document.querySelector('[data-text-color="red"]')!);
    await waitFor(() => expect(screen.getByTestId("value")).toHaveTextContent("{{red:First}}"));
    expect(onChange).toHaveBeenCalledWith(expect.stringContaining("{{red:First}}"));
  });

  it("uses the selected hard-break line for wrap and preserves the fine desktop toolbar", async () => {
    const resize = mediaAt(640);
    const user = userEvent.setup();
    const { wrap, align } = mountEditor();
    const surface = await screen.findByRole("textbox", { name: "Template editor" });
    const editor = (surface as TiptapEditorHTMLElement).editor!;
    await waitFor(() =>
      expect(document.querySelector('[data-slot="charset-editor-host"]')).toHaveAttribute("data-toolbar", "tablet"),
    );
    let secondLineStart = 1;
    editor.state.doc.descendants((node, pos) => {
      if (node.type.name === "hardBreak" && secondLineStart === 1) secondLineStart = pos + 1;
    });
    act(() => editor.commands.setTextSelection(secondLineStart));
    await user.click(screen.getByRole("button", { name: "More" }));
    expect(screen.getByRole("switch", { name: "Wrap this line" })).toBeChecked();
    await user.click(screen.getByRole("switch", { name: "Wrap this line" }));
    expect(wrap).toHaveBeenCalledWith(1, false);
    await user.keyboard("{Escape}");
    await user.click(screen.getByRole("button", { name: "Align center" }));
    expect(align).toHaveBeenCalledWith(1, "center");
    resize(1024);
    await waitFor(() =>
      expect(document.querySelector('[data-slot="charset-editor-host"]')).toHaveAttribute("data-toolbar", "kit"),
    );
    expect(screen.getByRole("button", { name: "Colors" })).toBeVisible();
    expect((surface as TiptapEditorHTMLElement).editor).toBe(editor);
  });
});
