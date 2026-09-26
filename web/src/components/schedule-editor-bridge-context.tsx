"use client";

import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

import type { ScheduleFormField, ScheduleStaging } from "@/lib/ai-choreography/types";

/** What the schedule form lends while it is open. */
export interface ScheduleFormHandle {
  setField: (field: ScheduleFormField, value: unknown) => void;
}

/** What the schedule page lends while it is mounted. */
export interface ScheduleEditorHandlers {
  /** Open a fresh, empty entry form (a new instance, nothing prefilled). */
  openEmpty: () => void;
  /** Open the form on an existing entry. */
  openEntry: (scheduleId: string) => void;
  /** Close the form without submitting. */
  close: () => void;
  /** The mounted form's handle, once the sheet has opened. */
  getForm: () => ScheduleFormHandle | null;
}

interface ScheduleEditorBridgeContextValue {
  /** True while the schedule page is mounted and registered. */
  hasScheduleEditor: boolean;
  /** The staging surface the walkthrough drives; every method is safe with no page. */
  staging: ScheduleStaging;
  /** Called by the schedule page to register itself. */
  register: (handlers: ScheduleEditorHandlers) => void;
  /** Called by the schedule page when it unmounts. */
  unregister: () => void;
}

const ScheduleEditorBridgeContext = createContext<ScheduleEditorBridgeContextValue | null>(null);

const DEFAULT_WAIT_MS = 3000;
const POLL_MS = 50;

export function ScheduleEditorBridgeProvider({ children }: { children: React.ReactNode }) {
  const [hasScheduleEditor, setHasScheduleEditor] = useState(false);
  const handlersRef = useRef<ScheduleEditorHandlers | null>(null);
  const waitersRef = useRef<Array<(ok: boolean) => void>>([]);

  const register = useCallback((handlers: ScheduleEditorHandlers) => {
    handlersRef.current = handlers;
    setHasScheduleEditor(true);
    const waiters = waitersRef.current;
    waitersRef.current = [];
    for (const resolve of waiters) resolve(true);
  }, []);

  const unregister = useCallback(() => {
    handlersRef.current = null;
    setHasScheduleEditor(false);
  }, []);

  const staging = useMemo<ScheduleStaging>(
    () => ({
      isMounted: () => handlersRef.current !== null,
      openEmpty: () => handlersRef.current?.openEmpty(),
      openEntry: (id) => handlersRef.current?.openEntry(id),
      setField: (field, value) => handlersRef.current?.getForm()?.setField(field, value),
      close: () => handlersRef.current?.close(),
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
      // The form mounts a frame or two after the sheet opens; poll for its
      // handle rather than wiring a second registration.
      waitForForm: (timeoutMs = DEFAULT_WAIT_MS) =>
        new Promise<boolean>((resolve) => {
          const started = Date.now();
          const probe = () => {
            if (handlersRef.current?.getForm()) return resolve(true);
            if (Date.now() - started >= timeoutMs) return resolve(false);
            window.setTimeout(probe, POLL_MS);
          };
          probe();
        }),
    }),
    [],
  );

  const value = useMemo<ScheduleEditorBridgeContextValue>(
    () => ({ hasScheduleEditor, staging, register, unregister }),
    [hasScheduleEditor, staging, register, unregister],
  );

  return <ScheduleEditorBridgeContext.Provider value={value}>{children}</ScheduleEditorBridgeContext.Provider>;
}

export function useScheduleEditorBridge(): ScheduleEditorBridgeContextValue {
  const ctx = useContext(ScheduleEditorBridgeContext);
  if (!ctx) {
    throw new Error("useScheduleEditorBridge must be used within ScheduleEditorBridgeProvider");
  }
  return ctx;
}
