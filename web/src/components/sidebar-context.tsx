"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

const STORAGE_KEY = "fiestaboard_sidebar_collapsed";

interface SidebarContextValue {
  collapsed: boolean;
  transitioning: boolean;
  toggle: () => void;
  /**
   * Programmatically set the collapsed state. Pass `persist: false` for
   * scoped overrides (e.g. the editor auto-collapsing the sidebar to
   * give the AI chat panel more room) so the user's stored preference
   * isn't overwritten.
   */
  setCollapsed: (value: boolean, opts?: { persist?: boolean }) => void;
  onTransitionEnd: () => void;
}

const SidebarContext = createContext<SidebarContextValue>({
  collapsed: false,
  transitioning: false,
  toggle: () => {},
  setCollapsed: () => {},
  onTransitionEnd: () => {},
});

export function SidebarProvider({ children }: { children: React.ReactNode }) {
  const [collapsed, setCollapsedState] = useState(false);
  const [transitioning, setTransitioning] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "true") setCollapsedState(true);
    } catch {}
  }, []);

  const setCollapsed = useCallback(
    (value: boolean, opts?: { persist?: boolean }) => {
      setCollapsedState((prev) => {
        if (prev === value) return prev;
        setTransitioning(true);
        if (opts?.persist !== false) {
          try {
            localStorage.setItem(STORAGE_KEY, String(value));
          } catch {}
        }
        return value;
      });
    },
    [],
  );

  const toggle = useCallback(() => {
    setTransitioning(true);
    setCollapsedState((prev) => {
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

  // Memoize the context value so consumers that depend on the
  // identity of the value object (e.g. effects with the sidebar in
  // their dep list) only re-run when state actually changes.
  const value = useMemo(
    () => ({ collapsed, transitioning, toggle, setCollapsed, onTransitionEnd }),
    [collapsed, transitioning, toggle, setCollapsed, onTransitionEnd],
  );

  return (
    <SidebarContext.Provider value={value}>
      {children}
    </SidebarContext.Provider>
  );
}

export function useSidebar() {
  return useContext(SidebarContext);
}
