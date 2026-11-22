import { createContext, type ReactNode, useContext, useEffect } from "react";

type RenderItems = () => ReactNode;
type Register = (render: RenderItems | null) => void;

/**
 * The section header's "Integration options" menu (07d `324:40267`) also
 * carries the open detail pane's per-plugin actions: 07d's pane has no switch
 * or "…" of its own (BB-FC-9). The layout owns the menu, the pane owns the
 * actions, so the pane registers a render function here.
 */
export const IntegrationPaneMenuContext = createContext<Register | null>(null);

/** Registers `render` while `active`; the menu calls it each time it opens. */
export function useIntegrationPaneMenu(active: boolean, render: RenderItems) {
  const register = useContext(IntegrationPaneMenuContext);
  useEffect(() => {
    if (!active || !register) return;
    register(render);
  });
  useEffect(() => {
    if (!active || !register) return;
    return () => register(null);
  }, [active, register]);
}
