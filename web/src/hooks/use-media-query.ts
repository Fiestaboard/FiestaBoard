import { useCallback, useSyncExternalStore } from "react";

/**
 * Whether a CSS media query matches, kept live. The server snapshot is
 * `false`, so a hydrating render agrees with the server and then corrects.
 */
export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onChange: () => void) => {
      const list = window.matchMedia?.(query);
      list?.addEventListener("change", onChange);
      return () => list?.removeEventListener("change", onChange);
    },
    [query],
  );
  return useSyncExternalStore(
    subscribe,
    () => !!window.matchMedia?.(query)?.matches,
    () => false,
  );
}
