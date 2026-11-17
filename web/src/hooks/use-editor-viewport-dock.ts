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
  // Pair height with this render's inset, even if another resize happens before
  // the passive effect runs. A newer live height could consume the contraction.
  const height = viewport?.height ?? 0;

  const previousHeight = useRef(height);
  const pendingContraction = useRef(false);

  // Run after React commits the padding returned below. Scheduling directly
  // from the native resize listener can scroll against the old document height.
  useEffect(() => {
    const contracted = height < previousHeight.current;
    previousHeight.current = height;
    if (!enabled || !viewport || bottom <= 0 || viewport.scale !== 1) {
      pendingContraction.current = false;
      return;
    }
    const templateHasFocus = () => {
      const active = document.activeElement;
      return (
        active !== null && contentRef.current?.contains(active) && active.matches('textarea, [contenteditable="true"]')
      );
    };
    if (!templateHasFocus()) {
      pendingContraction.current = false;
      return;
    }
    if (contracted) pendingContraction.current = true;
    if (!pendingContraction.current) return;
    // A pan can change the inset before these frames run. Preserve only the
    // outstanding contraction so that new committed space gets another turn.
    let scrollFrame = 0;
    const layoutFrame = requestAnimationFrame(() => {
      scrollFrame = requestAnimationFrame(() => {
        pendingContraction.current = false;
        if (templateHasFocus()) previewRef.current?.scrollIntoView({ block: "start", behavior: "instant" });
      });
    });
    return () => {
      cancelAnimationFrame(layoutFrame);
      cancelAnimationFrame(scrollFrame);
    };
  }, [bottom, height, enabled, viewport, contentRef, previewRef]);

  return enabled ? bottom : 0;
}
