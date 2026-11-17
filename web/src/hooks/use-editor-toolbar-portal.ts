import { useEffect, useState } from "react";

/**
 * Fixed editor tools must escape the editor's contained layout, while their
 * portaled DOM still belongs to a named landmark. Each mounted editor owns
 * its host so leaving touch mode or closing the editor removes it completely.
 */
export function useEditorToolbarPortal(enabled: boolean, label: string): HTMLElement | null {
  const [host] = useState(() => (typeof document === "undefined" ? null : document.createElement("section")));

  useEffect(() => {
    host?.setAttribute("aria-label", label);
  }, [host, label]);

  useEffect(() => {
    if (!enabled || !host) return;
    document.body.appendChild(host);
    return () => host.remove();
  }, [enabled, host]);

  return enabled ? host : null;
}
