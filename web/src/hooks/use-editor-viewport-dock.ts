import { type RefObject, useEffect } from "react";

import { useVisualViewportBottom } from "@/hooks/use-visual-viewport-bottom";

/** Keep the dock reachable when a focused template's visible viewport contracts. */
export function useEditorViewportDock(
  enabled: boolean,
  contentRef: RefObject<HTMLElement | null>,
  previewRef: RefObject<HTMLElement | null>,
) {
  // Include scale in the snapshot's result: zoom can change without changing
  // the numeric inset, and must still clear the reserved document space.
  const bottom = useVisualViewportBottom(true);
  const viewport = typeof window === "undefined" ? null : window.visualViewport;

  useEffect(() => {
    if (!enabled || !viewport) return;
    let height = viewport.height;
    let layoutFrame = 0;
    let scrollFrame = 0;
    const cancel = () => {
      cancelAnimationFrame(layoutFrame);
      cancelAnimationFrame(scrollFrame);
    };
    const templateHasFocus = () => {
      const active = document.activeElement;
      return (
        active !== null && contentRef.current?.contains(active) && active.matches('textarea, [contenteditable="true"]')
      );
    };
    const resize = () => {
      const contracted = viewport.height < height;
      height = viewport.height;
      cancel();
      if (!contracted || viewport.scale !== 1 || !templateHasFocus()) return;
      // React must commit the new scroll space, then the browser must lay it
      // out before scrollIntoView can use it. Never move focus or the caret.
      layoutFrame = requestAnimationFrame(() => {
        scrollFrame = requestAnimationFrame(() => {
          if (templateHasFocus()) previewRef.current?.scrollIntoView({ block: "start", behavior: "instant" });
        });
      });
    };
    viewport.addEventListener("resize", resize);
    return () => {
      cancel();
      viewport.removeEventListener("resize", resize);
    };
  }, [enabled, viewport, contentRef, previewRef]);

  return enabled ? bottom : 0;
}
