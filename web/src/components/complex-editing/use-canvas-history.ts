"use client";

import { useCallback, useMemo, useState } from "react";

import type { CanvasContent } from "@/lib/api";

const LIMIT = 50;

type Content = CanvasContent | null | undefined;

/** What the pixel pad writes: the only part of the content its history owns. */
interface PadState {
  size?: CanvasContent["size"];
  pixels?: string[];
  palette?: Record<string, string>;
}

const padState = (content: Content): PadState => ({
  size: content?.size,
  pixels: content?.pixels,
  palette: content?.palette,
});

/**
 * Lay a pad snapshot over the current content. Shapes, background and every
 * other field stay as they are now, so an edit made in Shapes, Source or
 * Layers after a stroke survives the stroke's Undo. Palette keys that the
 * current shapes or background still name are kept too.
 */
function restore(current: Content, pad: PadState): CanvasContent {
  const next: CanvasContent = { ...(current ?? {}) };
  for (const key of ["size", "pixels"] as const) {
    if (pad[key] === undefined) delete next[key];
    else (next as Record<string, unknown>)[key] = pad[key];
  }
  const references = new Set(
    [current?.background, ...(current?.shapes ?? []).flatMap(Object.values)].filter(
      (value): value is string => typeof value === "string",
    ),
  );
  const kept = Object.fromEntries(
    Object.entries(current?.palette ?? {}).filter(([key]) => references.has(key) && !(key in (pad.palette ?? {}))),
  );
  const palette = { ...(pad.palette ?? {}), ...kept };
  if (pad.palette === undefined && Object.keys(kept).length === 0) delete next.palette;
  else next.palette = palette;
  return next;
}

/**
 * 04b `135:140352` History for the pixel pad: each committed stroke, fill or
 * clear is one step. Undo/redo restore only the pad's pixels, palette and
 * size over the current content, through the same change callback, so the
 * page's draft and preview follow and edits in the other tabs are kept.
 */
export function useCanvasHistory(content: Content, onContentChange: (content: CanvasContent) => void) {
  const [stacks, setStacks] = useState<{ past: PadState[]; future: PadState[] }>({ past: [], future: [] });

  const commit = useCallback(
    (next: CanvasContent) => {
      setStacks((s) => ({ past: [...s.past, padState(content)].slice(-LIMIT), future: [] }));
      onContentChange(next);
    },
    [content, onContentChange],
  );
  const undo = useCallback(() => {
    if (stacks.past.length === 0) return;
    const previous = stacks.past[stacks.past.length - 1];
    setStacks({ past: stacks.past.slice(0, -1), future: [padState(content), ...stacks.future] });
    onContentChange(restore(content, previous));
  }, [content, onContentChange, stacks]);
  const redo = useCallback(() => {
    if (stacks.future.length === 0) return;
    const [next, ...rest] = stacks.future;
    setStacks({ past: [...stacks.past, padState(content)].slice(-LIMIT), future: rest });
    onContentChange(restore(content, next));
  }, [content, onContentChange, stacks]);

  return useMemo(
    () => ({ commit, undo, redo, canUndo: stacks.past.length > 0, canRedo: stacks.future.length > 0 }),
    [commit, undo, redo, stacks],
  );
}
