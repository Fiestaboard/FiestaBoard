import { act, render, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ScheduleEditorBridgeProvider, useScheduleEditorBridge } from "@/components/schedule-editor-bridge-context";

function wrapper({ children }: { children: React.ReactNode }) {
  return <ScheduleEditorBridgeProvider>{children}</ScheduleEditorBridgeProvider>;
}

describe("ScheduleEditorBridgeProvider", () => {
  it("hasScheduleEditor is false before register and true after", () => {
    const { result } = renderHook(() => useScheduleEditorBridge(), { wrapper });
    expect(result.current.hasScheduleEditor).toBe(false);

    act(() => {
      result.current.register(() => {});
    });
    expect(result.current.hasScheduleEditor).toBe(true);

    act(() => {
      result.current.unregister();
    });
    expect(result.current.hasScheduleEditor).toBe(false);
  });

  it("openScheduleForm invokes the registered handler with prefill", () => {
    const handler = vi.fn();
    const { result } = renderHook(() => useScheduleEditorBridge(), { wrapper });

    act(() => {
      result.current.register(handler);
    });

    act(() => {
      result.current.openScheduleForm({
        page_id: "abc",
        start_time: "07:00",
        end_time: "09:00",
        day_pattern: "weekdays",
      });
    });

    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith({
      page_id: "abc",
      start_time: "07:00",
      end_time: "09:00",
      day_pattern: "weekdays",
    });
  });

  it("openScheduleForm with no prefill calls the handler with undefined", () => {
    const handler = vi.fn();
    const { result } = renderHook(() => useScheduleEditorBridge(), { wrapper });

    act(() => {
      result.current.register(handler);
    });
    act(() => {
      result.current.openScheduleForm();
    });

    expect(handler).toHaveBeenCalledWith(undefined);
  });

  it("openScheduleForm after unregister is a no-op", () => {
    const handler = vi.fn();
    const { result } = renderHook(() => useScheduleEditorBridge(), { wrapper });

    act(() => {
      result.current.register(handler);
    });
    act(() => {
      result.current.unregister();
    });
    act(() => {
      result.current.openScheduleForm({ page_id: "abc" });
    });

    expect(handler).not.toHaveBeenCalled();
  });

  it("throws when used outside the provider", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<TestConsumer />)).toThrow(/must be used within ScheduleEditorBridgeProvider/);
    consoleError.mockRestore();
  });
});

function TestConsumer() {
  useScheduleEditorBridge();
  return null;
}
