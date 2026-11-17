import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useAppBadge } from "@/hooks/use-app-badge";
import {
  clearAppBadge,
  MORE_VISIBILITY_EVENT,
  moreVisibilityChanged,
  observeMoreVisibility,
} from "@/lib/pwa/app-badge";

const setBadge = vi.fn();
const clearBadge = vi.fn();
beforeEach(() => {
  setBadge.mockReset().mockResolvedValue(undefined);
  clearBadge.mockReset().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "setAppBadge", { configurable: true, value: setBadge });
  Object.defineProperty(navigator, "clearAppBadge", { configurable: true, value: clearBadge });
});
afterEach(() => {
  Reflect.deleteProperty(navigator, "setAppBadge");
  Reflect.deleteProperty(navigator, "clearAppBadge");
});

describe("app attention badge", () => {
  it("acknowledges actual More visibility, not a click or mounted hidden footer", async () => {
    const boundary = document.createElement("div");
    boundary.setAttribute("aria-hidden", "true");
    const slot = document.createElement("div");
    boundary.append(slot);
    document.body.append(boundary);
    const changes: boolean[] = [];
    const listener = (event: Event) => changes.push((event as CustomEvent).detail.open);
    window.addEventListener(MORE_VISIBILITY_EVENT, listener);
    const stop = observeMoreVisibility(slot);
    expect(changes).toEqual([false]);
    boundary.setAttribute("aria-hidden", "false");
    await waitFor(() => expect(changes).toEqual([false, true]));
    stop();
    boundary.remove();
    window.removeEventListener(MORE_VISIBILITY_EVENT, listener);
    expect(changes).toEqual([false, true, false]);
  });
  it("sets an attention dot, never a message count, and clears on More open", async () => {
    const { rerender } = renderHook(({ attention }) => useAppBadge(attention), {
      initialProps: { attention: "update:11.1" },
    });
    await waitFor(() => expect(setBadge).toHaveBeenCalledWith());
    act(() => moreVisibilityChanged(true));
    await waitFor(() => expect(clearBadge).toHaveBeenCalledOnce());
    act(() => moreVisibilityChanged(false));
    rerender({ attention: "update:11.1" });
    expect(setBadge).toHaveBeenCalledTimes(1);
    rerender({ attention: "update:11.2" });
    await waitFor(() => expect(setBadge).toHaveBeenCalledTimes(2));
  });
  it("does not re-badge attention that arrives while More is open", async () => {
    const { rerender } = renderHook(({ attention }) => useAppBadge(attention), { initialProps: { attention: "" } });
    act(() => moreVisibilityChanged(true));
    rerender({ attention: "setup:weather" });
    expect(setBadge).not.toHaveBeenCalled();
    act(() => moreVisibilityChanged(false));
    rerender({ attention: "setup:weather" });
    expect(setBadge).not.toHaveBeenCalled();
  });
  it("clears when attention resolves", async () => {
    const { rerender } = renderHook(({ attention }) => useAppBadge(attention), {
      initialProps: { attention: "setup:weather" },
    });
    rerender({ attention: "" });
    await waitFor(() => expect(clearBadge).toHaveBeenCalledOnce());
  });
  it("tolerates missing APIs, rejected promises and synchronous browser failures", async () => {
    Reflect.deleteProperty(navigator, "setAppBadge");
    Reflect.deleteProperty(navigator, "clearAppBadge");
    renderHook(() => useAppBadge("update:11.1"));
    await expect(clearAppBadge()).resolves.toBeUndefined();
    Object.defineProperty(navigator, "clearAppBadge", {
      configurable: true,
      value: () => {
        throw new Error("blocked");
      },
    });
    await expect(clearAppBadge()).resolves.toBeUndefined();
    Object.defineProperty(navigator, "clearAppBadge", {
      configurable: true,
      value: () => Promise.reject(new Error("blocked")),
    });
    await expect(clearAppBadge()).resolves.toBeUndefined();
  });
});
