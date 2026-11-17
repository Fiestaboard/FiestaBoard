import { type RefObject, useEffect, useRef } from "react";

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

  const previousHeight = useRef(viewport?.height ?? 0);

  // Run after React commits the padding returned below. Scheduling directly
  // from the native resize listener can scroll against the old document height.
  useEffect(() => {
    const height = viewport?.height ?? 0;
    const contracted = height < previousHeight.current;
    previousHeight.current = height;
    if (!enabled || !viewport || bottom <= 0 || !contracted || viewport.scale !== 1) return;
    const templateHasFocus = () => {
      const active = document.activeElement;
      return (
        active !== null && contentRef.current?.contains(active) && active.matches('textarea, [contenteditable="true"]')
      );
    };
    if (!templateHasFocus()) return;
    let scrollFrame = 0;
    const layoutFrame = requestAnimationFrame(() => {
      scrollFrame = requestAnimationFrame(() => {
        if (templateHasFocus()) previewRef.current?.scrollIntoView({ block: "start", behavior: "instant" });
      });
    });
    return () => {
      cancelAnimationFrame(layoutFrame);
      cancelAnimationFrame(scrollFrame);
    };
  }, [bottom, enabled, viewport, contentRef, previewRef]);

  return enabled ? bottom : 0;
}
