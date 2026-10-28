"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

interface GlobalAiPanelContextValue {
  isOpen: boolean;
  isMinimized: boolean;
  open: () => void;
  close: () => void;
  minimize: () => void;
}

const GlobalAiPanelContext = createContext<GlobalAiPanelContextValue | null>(null);

export function GlobalAiPanelProvider({ children }: { children: React.ReactNode }) {
  const [mode, setMode] = useState<"closed" | "open" | "minimized">("closed");
  const open = useCallback(() => setMode("open"), []);
  const close = useCallback(() => setMode("closed"), []);
  const minimize = useCallback(() => setMode("minimized"), []);
  const value = useMemo(
    () => ({ isOpen: mode === "open", isMinimized: mode === "minimized", open, close, minimize }),
    [mode, open, close, minimize],
  );

  return <GlobalAiPanelContext.Provider value={value}>{children}</GlobalAiPanelContext.Provider>;
}

/** Optional for app chrome also rendered independently in Storybook. */
export function useOptionalGlobalAiPanel(): GlobalAiPanelContextValue | null {
  return useContext(GlobalAiPanelContext);
}

export function useGlobalAiPanel(): GlobalAiPanelContextValue {
  const ctx = useContext(GlobalAiPanelContext);
  if (!ctx) throw new Error("useGlobalAiPanel must be used within GlobalAiPanelProvider");
  return ctx;
}
