import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  ScheduleEditorBridgeProvider,
  type ScheduleEditorHandlers,
  useScheduleEditorBridge,
} from "@/components/schedule-editor-bridge-context";

const wrapper = ({ children }: { children: React.ReactNode }) => (
  <ScheduleEditorBridgeProvider>{children}</ScheduleEditorBridgeProvider>
);

function handlers(overrides: Partial<ScheduleEditorHandlers> = {}): ScheduleEditorHandlers {
  return { openEmpty: vi.fn(), openEntry: vi.fn(), close: vi.fn(), getForm: () => null, ...overrides };
}

describe("ScheduleEditorBridge", () => {
  it("reports whether the schedule page is mounted", () => {
    const { result } = renderHook(() => useScheduleEditorBridge(), { wrapper });
    expect(result.current.hasScheduleEditor).toBe(false);
    expect(result.current.staging.isMounted()).toBe(false);
    act(() => result.current.register(handlers()));
    expect(result.current.hasScheduleEditor).toBe(true);
    act(() => result.current.unregister());
    expect(result.current.hasScheduleEditor).toBe(false);
  });

  it("forwards the staging calls to the registered page and its form", () => {
    const setField = vi.fn();
    const h = handlers({ getForm: () => ({ setField }) });
    const { result } = renderHook(() => useScheduleEditorBridge(), { wrapper });
    act(() => result.current.register(h));
    result.current.staging.openEmpty();
    result.current.staging.openEntry("s1");
    result.current.staging.setField("start_time", "06:45");
    result.current.staging.close();
    expect(h.openEmpty).toHaveBeenCalled();
    expect(h.openEntry).toHaveBeenCalledWith("s1");
    expect(setField).toHaveBeenCalledWith("start_time", "06:45");
    expect(h.close).toHaveBeenCalled();
  });

  it("is safe to drive with no page mounted", () => {
    const { result } = renderHook(() => useScheduleEditorBridge(), { wrapper });
    expect(() => {
      result.current.staging.openEmpty();
      result.current.staging.setField("enabled", true);
      result.current.staging.close();
    }).not.toThrow();
  });

  it("waitFor resolves when the page registers, and false on timeout", async () => {
    vi.useFakeTimers();
    try {
      const { result } = renderHook(() => useScheduleEditorBridge(), { wrapper });
      const pending = result.current.staging.waitFor(1000);
      act(() => result.current.register(handlers()));
      await expect(pending).resolves.toBe(true);
      act(() => result.current.unregister());
      const timeout = result.current.staging.waitFor(200);
      await vi.advanceTimersByTimeAsync(250);
      await expect(timeout).resolves.toBe(false);
    } finally {
      vi.useRealTimers();
    }
  });

  it("waitForForm polls until the form handle exists", async () => {
    vi.useFakeTimers();
    try {
      let form: { setField: () => void } | null = null;
      const { result } = renderHook(() => useScheduleEditorBridge(), { wrapper });
      act(() => result.current.register(handlers({ getForm: () => form })));
      const pending = result.current.staging.waitForForm(1000);
      await vi.advanceTimersByTimeAsync(120);
      form = { setField: vi.fn() };
      await vi.advanceTimersByTimeAsync(120);
      await expect(pending).resolves.toBe(true);
    } finally {
      vi.useRealTimers();
    }
  });
});
