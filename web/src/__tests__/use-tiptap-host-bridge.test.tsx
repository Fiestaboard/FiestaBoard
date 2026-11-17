import { act, renderHook, waitFor } from "@testing-library/react";
import { Editor } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import { expect, it } from "vitest";

import { useTiptapHostBridge } from "@/hooks/use-tiptap-host-bridge";

it("discovers the typed TipTap root, follows hard-break selection ranges and releases it on removal", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = { current: host };
  const { result, unmount } = renderHook(() => useTiptapHostBridge(root));
  expect(result.current.editor).toBeNull();
  let editor!: Editor;
  act(() => {
    editor = new Editor({ element: host, extensions: [StarterKit], content: "<p>one<br>two<br>three</p>" });
  });
  try {
    await waitFor(() => expect(result.current.editor).toBe(editor));
    act(() => editor.commands.setTextSelection({ from: 2, to: 11 }));
    expect(result.current).toMatchObject({ firstLine: 0, lastLine: 2 });
    act(() => editor.commands.setTextSelection(7));
    expect(result.current).toMatchObject({ firstLine: 1, lastLine: 1 });
    act(() => {
      editor.destroy();
      host.replaceChildren();
    });
    await waitFor(() => expect(result.current.editor).toBeNull());
  } finally {
    unmount();
    if (!editor.isDestroyed) editor.destroy();
    host.remove();
  }
});
