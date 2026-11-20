"use client";

import { type RefObject, useEffect, useState } from "react";

export interface EditorScrollMargin {
  top: number;
  bottom: number;
}

/** Room kept between the caret and a docked bar, so the line stays readable. */
const GAP = 8;

function height(element: Element | null | undefined): number {
  return element ? element.getBoundingClientRect().height : 0;
}

/**
 * What covers the editor's scroll area on a phone (BB-B-5): the sticky header
 * and the docked preview at the top, the fixed touch toolbar (lifted by the
 * on-screen keyboard's `keyboardInset`) at the bottom. The template keeps its
 * caret inside what is left, and the scroll container's `scroll-padding`
 * says the same for native scrolling (the plain-text field, focus moves).
 *
 * `undefined` when not docked: nothing covers the template then. `enabled`
 * must turn true only once the editor (not its loading state) is mounted.
 */
export function useEditorScrollMargin(
  enabled: boolean,
  rootRef: RefObject<HTMLElement | null>,
  keyboardInset: number,
): EditorScrollMargin | undefined {
  const [margin, setMargin] = useState<EditorScrollMargin | undefined>(undefined);

  useEffect(() => {
    const root = rootRef.current;
    if (!enabled || !root) {
      setMargin(undefined);
      return;
    }
    const measure = () => {
      const header = root.querySelector('[data-slot="card-header"]');
      const docked = root.querySelector('[data-slot="editor-preview"][data-variant="docked"]');
      // Only a preview that stays docked covers the template.
      const preview = docked && getComputedStyle(docked).position === "sticky" ? docked : null;
      // The touch toolbar is fixed to the viewport and may be portalled out.
      const toolbar = document.querySelector('[data-slot="editor-toolbar"][data-size="touch"]');
      const next = {
        top: Math.round(height(header) + height(preview)) + GAP,
        bottom: Math.round(height(toolbar) + keyboardInset) + GAP,
      };
      setMargin((previous) =>
        previous && previous.top === next.top && previous.bottom === next.bottom ? previous : next,
      );
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(root);
    for (const element of [
      root.querySelector('[data-slot="card-header"]'),
      root.querySelector('[data-slot="editor-preview"]'),
      document.querySelector('[data-slot="editor-toolbar"]'),
    ]) {
      if (element) observer.observe(element);
    }
    return () => observer.disconnect();
  }, [enabled, rootRef, keyboardInset]);

  // Native scrolling (focus moves, the plain-text field) honours the scroll
  // container's scroll-padding; ProseMirror takes the margin as a prop.
  useEffect(() => {
    const scroller = rootRef.current?.closest<HTMLElement>('[data-slot="page-editor-scroll"]');
    if (!scroller) return;
    scroller.style.scrollPaddingTop = margin ? `${margin.top}px` : "";
    scroller.style.scrollPaddingBottom = margin ? `${margin.bottom}px` : "";
  }, [margin, rootRef]);

  return margin;
}
