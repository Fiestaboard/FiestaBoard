"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

import type { CurrentPageSnapshot } from "@/lib/ai-chat-types";
import type { PageEditorStaging } from "@/lib/ai-choreography/types";

/**
 * What a mounted page editor lends to the rest of the app: a snapshot of
 * the draft for the AI's context, and the staging controls the walkthrough
 * uses to type a page in for real while the server creates it.
 */
export interface EditorHandlers {
  getSnapshot: () => CurrentPageSnapshot | null;
  getPageId: () => string | undefined;
  hasUnsavedChanges: () => boolean;
  beginStaging: () => void;
  stageName: (value: string) => void;
  stageLine: (index: number, value: string) => void;
  stageDeviceType: (value: string) => void;
  discardStaging: () => void;
  reloadFromServer: () => Promise<void>;
}

interface PageEditorBridgeContextValue {
  /** True while a page editor is mounted and registered. */
  hasEditor: boolean;
  /** Get the current page snapshot from the editor. Called lazily at turn time. */
  getEditorSnapshot: () => CurrentPageSnapshot | null;
  /** The staging surface the walkthrough drives; every method is safe with no editor. */
  staging: PageEditorStaging;
  /** Called by the page editor to register itself. */
  register: (handlers: EditorHandlers) => void;
  /** Called by the page editor when it unmounts. */
  unregister: () => void;
}

const PageEditorBridgeContext = createContext<PageEditorBridgeContextValue | null>(null);

const DEFAULT_WAIT_MS = 4000;

export function PageEditorBridgeProvider({ children }: { children: React.ReactNode }) {
  const [hasEditor, setHasEditor] = useState(false);
  const handlersRef = useRef<EditorHandlers | null>(null);
  // Resolved when the next editor registers, so a walkthrough can wait out
  // the route transition it just started.
  const waitersRef = useRef<Array<(ok: boolean) => void>>([]);

  const register = useCallback((handlers: EditorHandlers) => {
    handlersRef.current = handlers;
    setHasEditor(true);
    const waiters = waitersRef.current;
    waitersRef.current = [];
    for (const resolve of waiters) resolve(true);
  }, []);

  const unregister = useCallback(() => {
    handlersRef.current = null;
    setHasEditor(false);
  }, []);

  const getEditorSnapshot = useCallback(() => handlersRef.current?.getSnapshot() ?? null, []);

  const staging = useMemo<PageEditorStaging>(
    () => ({
      isMounted: () => handlersRef.current !== null,
      pageId: () => handlersRef.current?.getPageId(),
      hasUnsavedChanges: () => handlersRef.current?.hasUnsavedChanges() ?? false,
      begin: () => handlersRef.current?.beginStaging(),
      setName: (value) => handlersRef.current?.stageName(value),
      setLine: (index, value) => handlersRef.current?.stageLine(index, value),
      setDeviceType: (value) => handlersRef.current?.stageDeviceType(value),
      discard: () => handlersRef.current?.discardStaging(),
      reload: () => handlersRef.current?.reloadFromServer() ?? Promise.resolve(),
      waitFor: (timeoutMs = DEFAULT_WAIT_MS) => {
        if (handlersRef.current) return Promise.resolve(true);
        return new Promise<boolean>((resolve) => {
          const timer = window.setTimeout(() => {
            waitersRef.current = waitersRef.current.filter((w) => w !== done);
            resolve(false);
          }, timeoutMs);
          const done = (ok: boolean) => {
            window.clearTimeout(timer);
            resolve(ok);
          };
          waitersRef.current.push(done);
        });
      },
    }),
    [],
  );

  const value = useMemo<PageEditorBridgeContextValue>(
    () => ({ hasEditor, getEditorSnapshot, staging, register, unregister }),
    [hasEditor, getEditorSnapshot, staging, register, unregister],
  );

  return <PageEditorBridgeContext.Provider value={value}>{children}</PageEditorBridgeContext.Provider>;
}

export function usePageEditorBridge(): PageEditorBridgeContextValue {
  const ctx = useContext(PageEditorBridgeContext);
  if (!ctx) {
    throw new Error("usePageEditorBridge must be used within PageEditorBridgeProvider");
  }
  return ctx;
}
