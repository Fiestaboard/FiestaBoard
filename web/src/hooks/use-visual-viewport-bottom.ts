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

/** Shared placement for body-portaled tools above the visible viewport edge. */
export function useVisualViewportBottom() {
  return useSyncExternalStore(subscribeViewport, bottomInset, () => 0);
}
