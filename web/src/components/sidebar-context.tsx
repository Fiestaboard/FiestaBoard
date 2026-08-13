"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

const STORAGE_KEY = "fiestaboard_sidebar_collapsed";

function readStoredCollapsed(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) === "true";
  } catch {
    return false;
  }
}

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
  // Read the stored preference in the initializer, not a mount effect: an
  // effect renders the sidebar expanded and then snaps it closed
  // (react-hooks/set-state-in-effect, issue #1568). Safe here because the app
  // is a static SPA (`ssr: false`) — there is no server render to mismatch.
  const [collapsed, setCollapsedState] = useState(readStoredCollapsed);
  const [transitioning, setTransitioning] = useState(false);

  const setCollapsed = useCallback((value: boolean, opts?: { persist?: boolean }) => {
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
  }, []);

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

  return <SidebarContext.Provider value={value}>{children}</SidebarContext.Provider>;
}

export function useSidebar() {
  return useContext(SidebarContext);
}
