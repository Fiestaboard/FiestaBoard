"use client";

import { Box } from "@fiestaboard/ui";
import { useCallback, useEffect, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";

// The drawer's left edge, as a control.
//
// A separator the user can move is a real widget, not a decoration: it is
// in the tab order, it carries its value in pixels, and every gesture a
// pointer can make has a key that does the same thing. Pointer events (not
// mouse events) so a pen and a finger drag it as well as a mouse; the move
// and release are listened for on the window, so a fast drag that outruns
// the 12px hit area keeps resizing instead of sticking.

/** How far one arrow press moves the edge, and one Shift+arrow press. */
const STEP = 16;
const COARSE_STEP = 64;

export interface AiDrawerResizeHandleProps {
  /** The drawer's current width in px — the separator's value. */
  width: number;
  minWidth: number;
  /** The widest this viewport allows, which is what the separator reports. */
  maxWidth: number;
  /** A new width was requested. The caller clamps and applies it. */
  onResize: (width: number) => void;
  /** Enter / Space: swap between the default width and the last custom one. */
  onToggle: () => void;
  /** Double-click: back to the default width. */
  onReset: () => void;
  /** True while a pointer drag is live, so the page can drop its transition. */
  onDraggingChange?: (dragging: boolean) => void;
}

export function AiDrawerResizeHandle({
  width,
  minWidth,
  maxWidth,
  onResize,
  onToggle,
  onReset,
  onDraggingChange,
}: AiDrawerResizeHandleProps) {
  const t = useTranslations("aiChatPanel");
  const [dragging, setDragging] = useState(false);
  // The drag's origin. Resizing from the ORIGIN rather than from the last
  // event keeps a drag exact: accumulating deltas drifts as soon as one
  // move is clamped at an end of the range.
  const originRef = useRef<{ x: number; width: number } | null>(null);

  const stopDragging = useCallback(() => {
    originRef.current = null;
    setDragging(false);
    onDraggingChange?.(false);
  }, [onDraggingChange]);

  useEffect(() => {
    if (!dragging) return;

    const move = (event: PointerEvent) => {
      const origin = originRef.current;
      if (!origin) return;
      // The drawer is anchored right: the edge moving LEFT makes it wider.
      onResize(origin.width + (origin.x - event.clientX));
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stopDragging);
    window.addEventListener("pointercancel", stopDragging);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stopDragging);
      window.removeEventListener("pointercancel", stopDragging);
    };
  }, [dragging, onResize, stopDragging]);

  const handlePointerDown = (event: React.PointerEvent<HTMLElement>) => {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    originRef.current = { x: event.clientX, width };
    setDragging(true);
    onDraggingChange?.(true);
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    const step = event.shiftKey ? COARSE_STEP : STEP;
    switch (event.key) {
      case "ArrowLeft":
        onResize(width + step);
        break;
      case "ArrowRight":
        onResize(width - step);
        break;
      case "Home":
        onResize(minWidth);
        break;
      case "End":
        onResize(maxWidth);
        break;
      case "Enter":
      case " ":
        onToggle();
        break;
      default:
        return;
    }
    // Only for keys this handle actually acts on: Space must not scroll the
    // transcript behind it, but Tab and the rest still belong to the page.
    event.preventDefault();
  };

  return (
    <Box
      role="separator"
      aria-orientation="vertical"
      aria-label={t("resizeHandle")}
      aria-valuenow={width}
      aria-valuemin={minWidth}
      aria-valuemax={maxWidth}
      tabIndex={0}
      data-dragging={dragging || undefined}
      data-testid="ai-drawer-resize-handle"
      onPointerDown={handlePointerDown}
      onKeyDown={handleKeyDown}
      onDoubleClick={onReset}
      // A 12px grab zone straddling the edge, with a 2px bar drawn inside
      // it: the target is finger-sized (2.5.8) while the affordance stays a
      // hairline until you reach for it. `touch-action: none` keeps a touch
      // drag from scrolling the page instead of resizing.
      className="group absolute -left-1.5 top-0 z-10 hidden h-full w-3 cursor-col-resize touch-none select-none items-center justify-center focus-ring lg:flex"
    >
      <Box
        aria-hidden="true"
        className="h-full w-0.5 rounded-full bg-transparent transition-colors duration-control group-hover:bg-border group-focus-visible:bg-ring group-data-[dragging]:bg-ring"
      />
    </Box>
  );
}
