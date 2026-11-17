/** WEB-14: a More attention dot, never an unread-message count. */
export const MORE_VISIBILITY_EVENT = "fiestaboard:more-visibility";
type BadgeNavigator = Navigator & { setAppBadge?: () => Promise<void>; clearAppBadge?: () => Promise<void> };

export async function setAppBadge(): Promise<void> {
  try {
    await (navigator as BadgeNavigator).setAppBadge?.();
  } catch {
    /* Optional browser capability. */
  }
}

export async function clearAppBadge(): Promise<void> {
  try {
    await (navigator as BadgeNavigator).clearAppBadge?.();
  } catch {
    /* Optional browser capability. */
  }
}

export function moreVisibilityChanged(open: boolean): void {
  window.dispatchEvent(new CustomEvent(MORE_VISIBILITY_EVENT, { detail: { open } }));
}

/**
 * Published Sidebar keeps its More slot mounted without exposing open state.
 * Observe the semantic visibility boundary, never translated labels or CSS.
 * TODO(FiestaUI): replace this bridge with a Sidebar onMenuOpenChange prop.
 */
export function observeMoreVisibility(element: HTMLElement): () => void {
  const boundary = element.closest("[aria-hidden]");
  if (!boundary) return () => {};
  const update = () => moreVisibilityChanged(boundary.getAttribute("aria-hidden") === "false");
  update();
  const observer = new MutationObserver(update);
  observer.observe(boundary, { attributes: true, attributeFilter: ["aria-hidden"] });
  return () => {
    observer.disconnect();
    moreVisibilityChanged(false);
  };
}
