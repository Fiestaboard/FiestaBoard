"use client";

import { useCallback, useState } from "react";

import type { CanvasContent } from "@/lib/api";

const LIMIT = 50;

type Content = CanvasContent | null | undefined;

/**
 * 04b `135:140352` History for the pixel pad: each committed stroke, fill or
 * clear is one step. Undo/redo write the earlier content back through the
 * same change callback, so the page's draft and preview follow.
 */
export function useCanvasHistory(content: Content, onContentChange: (content: CanvasContent) => void) {
  const [stacks, setStacks] = useState<{ past: Content[]; future: Content[] }>({ past: [], future: [] });

  const commit = useCallback(
    (next: CanvasContent) => {
      setStacks((s) => ({ past: [...s.past, content].slice(-LIMIT), future: [] }));
      onContentChange(next);
    },
    [content, onContentChange],
  );
  const undo = useCallback(() => {
    if (stacks.past.length === 0) return;
    const previous = stacks.past[stacks.past.length - 1];
    setStacks({ past: stacks.past.slice(0, -1), future: [content, ...stacks.future] });
    onContentChange(previous ?? {});
  }, [content, onContentChange, stacks]);
  const redo = useCallback(() => {
    if (stacks.future.length === 0) return;
    const [next, ...rest] = stacks.future;
    setStacks({ past: [...stacks.past, content].slice(-LIMIT), future: rest });
    onContentChange(next ?? {});
  }, [content, onContentChange, stacks]);

  return { commit, undo, redo, canUndo: stacks.past.length > 0, canRedo: stacks.future.length > 0 };
}
