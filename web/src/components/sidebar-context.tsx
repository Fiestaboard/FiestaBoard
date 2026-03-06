"use client";

import { createContext, useContext, useState, useEffect, useCallback } from "react";

const STORAGE_KEY = "fiestaboard_sidebar_collapsed";

interface SidebarContextValue {
  collapsed: boolean;
  transitioning: boolean;
  toggle: () => void;
  onTransitionEnd: () => void;
}

const SidebarContext = createContext<SidebarContextValue>({
  collapsed: false,
  transitioning: false,
  toggle: () => {},
  onTransitionEnd: () => {},
});

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsed] = useState(false);
  const [transitioning, setTransitioning] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "true") setCollapsed(true);
    } catch {}
  }, []);

  const toggle = useCallback(() => {
    setTransitioning(true);
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(STORAGE_KEY, String(next));
      } catch {}
      return next;
    });
  }, []);

  const onTransitionEnd = useCallback(() => {
    setTransitioning(false);
  }, []);

  return (
    <SidebarContext.Provider value={{ collapsed, transitioning, toggle, onTransitionEnd }}>
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar() {
  return useContext(SidebarContext);
}
