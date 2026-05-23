"use client";

import {
  createContext,
  useCallback,
  useContext,
  useRef,
  useState,
} from "react";
import type { DayPattern } from "@/lib/api";

export interface ScheduleFormPrefill {
  page_id?: string;
  start_time?: string;
  end_time?: string | null;
  day_pattern?: DayPattern;
  custom_days?: string[];
}

interface ScheduleEditorBridgeContextValue {
  /** True while the schedule page is mounted and registered. */
  hasScheduleEditor: boolean;
  /** Open the new-entry form, optionally pre-filled. */
  openScheduleForm: (prefill?: ScheduleFormPrefill) => void;
  /** Called by the schedule page to register itself. */
  register: (handler: (prefill?: ScheduleFormPrefill) => void) => void;
  /** Called by the schedule page when it unmounts. */
  unregister: () => void;
}

const ScheduleEditorBridgeContext =
  createContext<ScheduleEditorBridgeContextValue | null>(null);

export function ScheduleEditorBridgeProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const [hasScheduleEditor, setHasScheduleEditor] = useState(false);
  const handlerRef = useRef<((prefill?: ScheduleFormPrefill) => void) | null>(
    null,
  );

  const register = useCallback(
    (handler: (prefill?: ScheduleFormPrefill) => void) => {
      handlerRef.current = handler;
      setHasScheduleEditor(true);
    },
    [],
  );

  const unregister = useCallback(() => {
    handlerRef.current = null;
    setHasScheduleEditor(false);
  }, []);

  const openScheduleForm = useCallback((prefill?: ScheduleFormPrefill) => {
    handlerRef.current?.(prefill);
  }, []);

  return (
    <ScheduleEditorBridgeContext.Provider
      value={{ hasScheduleEditor, openScheduleForm, register, unregister }}
    >
      {children}
    </ScheduleEditorBridgeContext.Provider>
  );
}

export function useScheduleEditorBridge(): ScheduleEditorBridgeContextValue {
  const ctx = useContext(ScheduleEditorBridgeContext);
  if (!ctx) {
    throw new Error(
      "useScheduleEditorBridge must be used within ScheduleEditorBridgeProvider",
    );
  }
  return ctx;
}
