import { useCallback, useSyncExternalStore } from "react";

/**
 * Whether a media query matches, without a hydration flip: the server
 * snapshot is `false` and the client re-renders with the real value.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = window.matchMedia?.(query);
      list?.addEventListener?.("change", onChange);
      return () => list?.removeEventListener?.("change", onChange);
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () => window.matchMedia?.(query)?.matches ?? false,
    () => false,
  );
}

/** Below Tailwind's `sm` (640 px): dialogs become bottom sheets (07a Web / Dialog shell · Mobile sheet). */
export const PHONE_QUERY = "(max-width: 639.98px)";
