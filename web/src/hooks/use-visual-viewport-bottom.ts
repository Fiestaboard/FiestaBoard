import { useSyncExternalStore } from "react";

function subscribeViewport(callback: () => void) {
  const viewport = window.visualViewport;
  viewport?.addEventListener("resize", callback);
  viewport?.addEventListener("scroll", callback);
  return () => {
    viewport?.removeEventListener("resize", callback);
    viewport?.removeEventListener("scroll", callback);
  };
}

function bottomInset() {
  const viewport = window.visualViewport;
  return viewport ? Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop) : 0;
}

function unzoomedBottomInset() {
  return window.visualViewport?.scale === 1 ? bottomInset() : 0;
}

/** Shared placement for body-portaled tools above the visible viewport edge. */
export function useVisualViewportBottom(unzoomedOnly = false) {
  return useSyncExternalStore(subscribeViewport, unzoomedOnly ? unzoomedBottomInset : bottomInset, () => 0);
}
