"use client";

import { createContext, useContext, useState } from "react";

interface GlobalAiPanelContextValue {
  isOpen: boolean;
  open: () => void;
  close: () => void;
}

const GlobalAiPanelContext = createContext<GlobalAiPanelContextValue | null>(null);

export function GlobalAiPanelProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <GlobalAiPanelContext.Provider
      value={{
        isOpen,
        open: () => setIsOpen(true),
        close: () => setIsOpen(false),
      }}
    >
      {children}
    </GlobalAiPanelContext.Provider>
  );
}

/**
 * The panel state where there may not be a provider — the Toaster reads it
 * to step out of the drawer's way, and it is also rendered on its own in
 * Storybook. Returns null rather than throwing.
 */
export function useOptionalGlobalAiPanel(): GlobalAiPanelContextValue | null {
  return useContext(GlobalAiPanelContext);
}

export function useGlobalAiPanel(): GlobalAiPanelContextValue {
  const ctx = useContext(GlobalAiPanelContext);
  if (!ctx) {
    throw new Error("useGlobalAiPanel must be used within GlobalAiPanelProvider");
  }
  return ctx;
}
