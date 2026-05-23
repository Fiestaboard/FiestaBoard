"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
} from "react";
import type { CurrentPageSnapshot, ToolCall } from "@/lib/ai-chat-types";

interface EditorHandlers {
  getSnapshot: () => CurrentPageSnapshot | null;
  applyOp: (call: ToolCall) => void;
  getCanUndo: () => boolean;
  undo: () => void;
}

interface PageEditorBridgeContextValue {
  /** True while a page editor is mounted and registered. */
  hasEditor: boolean;
  /** Get the current page snapshot from the editor. Called lazily at turn time. */
  getEditorSnapshot: () => CurrentPageSnapshot | null;
  /** Apply a page-editing op to the mounted editor. */
  applyEditorOp: (call: ToolCall) => void;
  /** Whether the editor can undo its last AI change. */
  canEditorUndo: () => boolean;
  /** Trigger undo in the editor. */
  editorUndo: () => void;
  /**
   * Resolves once a page editor is mounted (either already, or after the next
   * `register()` call). Resolves `true` on success and `false` on timeout so
   * the chaining loop never stalls. Used by `navigate_to_page` to wait out the
   * route transition before resuming the AI.
   */
  waitForEditor: (timeoutMs?: number) => Promise<boolean>;
  /** Called by the page editor to register itself. */
  register: (handlers: EditorHandlers) => void;
  /** Called by the page editor when it unmounts. */
  unregister: () => void;
}

const PageEditorBridgeContext = createContext<PageEditorBridgeContextValue | null>(null);

export function PageEditorBridgeProvider({ children }: { children: React.ReactNode }) {
  const [hasEditor, setHasEditor] = useState(false);
  // Incremented each time the AI applies a mutation so consumers
  // re-read canUndo() reactively after each change.
  const [mutationPulse, setMutationPulse] = useState(0);
  const handlersRef = useRef<EditorHandlers | null>(null);
  // Pending waiters resolved when the next editor registers. The AI chaining
  // loop uses these to wait out the route transition after navigate_to_page.
  const pendingWaitersRef = useRef<Array<(ok: boolean) => void>>([]);

  const register = useCallback((handlers: EditorHandlers) => {
    handlersRef.current = handlers;
    setHasEditor(true);
    if (pendingWaitersRef.current.length > 0) {
      const waiters = pendingWaitersRef.current;
      pendingWaitersRef.current = [];
      for (const resolve of waiters) resolve(true);
    }
  }, []);

  const unregister = useCallback(() => {
    handlersRef.current = null;
    setHasEditor(false);
    setMutationPulse(0);
  }, []);

  const waitForEditor = useCallback(
    (timeoutMs: number = 3000): Promise<boolean> => {
      if (handlersRef.current) return Promise.resolve(true);
      return new Promise<boolean>((resolve) => {
        let settled = false;
        const onReady = (ok: boolean) => {
          if (settled) return;
          settled = true;
          clearTimeout(timer);
          resolve(ok);
        };
        const timer = setTimeout(() => {
          // Remove this waiter so a late register() doesn't double-resolve.
          pendingWaitersRef.current = pendingWaitersRef.current.filter(
            (w) => w !== onReady,
          );
          onReady(false);
        }, timeoutMs);
        pendingWaitersRef.current.push(onReady);
      });
    },
    [],
  );

  const getEditorSnapshot = useCallback(
    () => handlersRef.current?.getSnapshot() ?? null,
    [],
  );

  const applyEditorOp = useCallback((call: ToolCall) => {
    handlersRef.current?.applyOp(call);
    setMutationPulse((p) => p + 1);
  }, []);

  // mutationPulse is listed as a dep so callers re-read this after
  // each AI mutation.
  const canEditorUndo = useCallback(
    // eslint-disable-next-line react-hooks/exhaustive-deps
    () => handlersRef.current?.getCanUndo() ?? false,
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mutationPulse],
  );

  const editorUndo = useCallback(() => {
    handlersRef.current?.undo();
    setMutationPulse((p) => p + 1);
  }, []);

  return (
    <PageEditorBridgeContext.Provider
      value={{
        hasEditor,
        getEditorSnapshot,
        applyEditorOp,
        canEditorUndo,
        editorUndo,
        waitForEditor,
        register,
        unregister,
      }}
    >
      {children}
    </PageEditorBridgeContext.Provider>
  );
}

export function usePageEditorBridge(): PageEditorBridgeContextValue {
  const ctx = useContext(PageEditorBridgeContext);
  if (!ctx) {
    throw new Error("usePageEditorBridge must be used within PageEditorBridgeProvider");
  }
  return ctx;
}
