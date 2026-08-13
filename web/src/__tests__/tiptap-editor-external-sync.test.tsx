/**
 * Regression test for issue #1586.
 *
 * When the editor is NOT focused (draft restore, tab switch, AI edit) the
 * component re-syncs its document from the incoming `value` prop. That sync
 * is meant to be silent: TipTap is told `emitUpdate: false` so the resulting
 * transaction is not reported back to the host as a user edit.
 *
 * The call used TipTap v2's `setContent(content, emitUpdate, parseOptions)`
 * signature. TipTap v3 collapsed those into `setContent(content, options)`,
 * so the `false` was destructured as an options object — `emitUpdate`
 * silently fell back to its `true` default and `parseOptions` was dropped
 * entirely. The sync therefore echoed straight back out through `onChange`,
 * which the page builder reads as a user edit (dirty state / undo churn).
 */
import { render, waitFor } from "@testing-library/react";
import type { ComponentProps } from "react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

import type { TipTapTemplateEditorHandle } from "@/components/tiptap-template-editor/TipTapTemplateEditor";
import { TipTapTemplateEditor } from "@/components/tiptap-template-editor/TipTapTemplateEditor";

type EditorProps = ComponentProps<typeof TipTapTemplateEditor>;

describe("TipTapTemplateEditor external value sync", () => {
  it("does not report an unfocused external sync back through onChange", async () => {
    const ref = createRef<TipTapTemplateEditorHandle>();
    const onChange = vi.fn();
    const props: EditorProps = {
      value: "HELLO\n\n\n\n\n",
      onChange,
      showToolbar: false,
      boardLines: 6,
      boardWidth: 22,
    };
    const { rerender } = render(<TipTapTemplateEditor ref={ref} {...props} />);
    await waitFor(() => expect(ref.current).not.toBeNull());
    onChange.mockClear();

    // Simulate a draft restore: a brand-new value arrives while the editor
    // is unfocused.
    rerender(<TipTapTemplateEditor ref={ref} {...props} value="RESTORED\n\n\n\n\n" />);

    // Let the deferred setContent (queueMicrotask) run.
    await new Promise((resolve) => setTimeout(resolve, 50));

    expect(onChange).not.toHaveBeenCalled();
  });
});
