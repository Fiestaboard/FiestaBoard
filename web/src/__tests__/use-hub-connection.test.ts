/**
 * Whether this browser can reach the hub, and whether it has a network at all.
 */
import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { isNoAnswer, useDeviceOnline } from "@/hooks/use-hub-connection";
import { ApiError } from "@/lib/api";

function setOnline(value: boolean) {
  Object.defineProperty(window.navigator, "onLine", { configurable: true, get: () => value });
}

afterEach(() => setOnline(true));

describe("isNoAnswer", () => {
  it("is true when the request never got a response", () => {
    expect(isNoAnswer(new TypeError("Failed to fetch"))).toBe(true);
    expect(isNoAnswer(new DOMException("timed out", "TimeoutError"))).toBe(true);
  });

  it("is true when the proxy says the hub behind it is gone", () => {
    expect(isNoAnswer(new ApiError("Bad Gateway", 502))).toBe(true);
    expect(isNoAnswer(new ApiError("Gateway Timeout", 504))).toBe(true);
  });

  it("is false for an answer from the hub itself", () => {
    expect(isNoAnswer(new ApiError("Service not initialized", 503))).toBe(false);
    expect(isNoAnswer(new ApiError("Unauthorized", 401))).toBe(false);
    expect(isNoAnswer(new ApiError("Server error", 500))).toBe(false);
  });

  it("is false with no error", () => {
    expect(isNoAnswer(null)).toBe(false);
    expect(isNoAnswer(undefined)).toBe(false);
  });
});

describe("useDeviceOnline", () => {
  it("follows the browser's online and offline events", () => {
    setOnline(true);
    const { result } = renderHook(() => useDeviceOnline());
    expect(result.current).toBe(true);

    act(() => {
      setOnline(false);
      window.dispatchEvent(new Event("offline"));
    });
    expect(result.current).toBe(false);

    act(() => {
      setOnline(true);
      window.dispatchEvent(new Event("online"));
    });
    expect(result.current).toBe(true);
  });
});
