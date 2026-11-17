import { useEffect, useRef } from "react";

import { clearAppBadge, MORE_VISIBILITY_EVENT, setAppBadge } from "@/lib/pwa/app-badge";

/** New attention may re-badge; closing More alone must not undo acknowledgement. */
export function useAppBadge(attention: string): void {
  const open = useRef(false);
  useEffect(() => {
    const changed = (event: Event) => {
      open.current = (event as CustomEvent<{ open: boolean }>).detail.open;
      if (open.current) void clearAppBadge();
    };
    window.addEventListener(MORE_VISIBILITY_EVENT, changed);
    return () => window.removeEventListener(MORE_VISIBILITY_EVENT, changed);
  }, []);
  useEffect(() => {
    if (attention && !open.current) void setAppBadge();
    else void clearAppBadge();
  }, [attention]);
}
