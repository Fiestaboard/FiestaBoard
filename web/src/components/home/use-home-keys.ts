import { useEffect, useRef } from "react";

/** A key typed into a field, an editor or a menu is the user's text, not a shortcut. */
function isTypingOrMenuTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  if (target.closest("input, textarea, select, [contenteditable='true'], [role='menu'], [role='dialog']")) {
    return true;
  }
  return false;
}

export interface HomeKeys {
  /** C: Compose a message. */
  onCompose: () => void;
  /** P: Change Page. */
  onChangePage: () => void;
  /** E: Edit page, when there is a page to edit. */
  onEditPage: (() => void) | null;
}

/**
 * Home's single-key shortcuts, as 07a draws their hints ("C Compose · P Change
 * Page", and P / C / E in the board menu). Bound on Home only; a key with a
 * modifier, a repeat, or one typed into a field, a menu or an open dialog is
 * left alone.
 */
export function useHomeKeys(keys: HomeKeys) {
  const ref = useRef(keys);
  useEffect(() => {
    ref.current = keys;
  });

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.repeat) return;
      if (event.metaKey || event.ctrlKey || event.altKey || event.shiftKey) return;
      if (isTypingOrMenuTarget(event.target)) return;
      if (document.querySelector("[role='dialog'], [role='alertdialog']")) return;
      const key = event.key.toLowerCase();
      const handler =
        key === "c"
          ? ref.current.onCompose
          : key === "p"
            ? ref.current.onChangePage
            : key === "e"
              ? ref.current.onEditPage
              : null;
      if (!handler) return;
      event.preventDefault();
      handler();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}
