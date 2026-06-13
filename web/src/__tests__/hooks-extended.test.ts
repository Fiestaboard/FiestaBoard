import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  getEffectiveBoardColor,
  getEffectiveDeviceType,
  queryKeys,
  useBoardSettings,
  usePagePreview,
  useSetActivePage,
} from "@/hooks/use-board";
import { ConfigOverridesProvider, SERVICE_KEYS, useConfigOverrides } from "@/hooks/use-config-overrides";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

describe("use-board extended", () => {
  describe("queryKeys", () => {
    it("has correct key structures", () => {
      expect(queryKeys.status).toEqual(["status"]);
      expect(queryKeys.config).toEqual(["config"]);
      expect(queryKeys.activePage).toEqual(["activePage"]);
      expect(queryKeys.pages).toEqual(["pages"]);
      expect(queryKeys.boardSettings).toEqual(["boardSettings"]);
      expect(queryKeys.pagePreview("p1")).toEqual(["pagePreview", "p1"]);
    });
  });

  describe("useSetActivePage", () => {
    it("sends mutation with page ID", async () => {
      const { result } = renderHook(() => useSetActivePage(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate("page-1");
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.status).toBe("success");
      expect(result.current.data?.page_id).toBe("page-1");
    });

    it("sends mutation with null to clear", async () => {
      const { result } = renderHook(() => useSetActivePage(), {
        wrapper: createWrapper(),
      });

      await act(async () => {
        result.current.mutate(null);
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.page_id).toBeNull();
    });

    it("invalidates board-current-message shortly after success and again as a safety net", async () => {
      // The backend's post-send adaptive refresh updates its cache within ~3s.
      // We invalidate twice from the client: once at ~750ms to catch the
      // fast local-API case, and once at ~3500ms after the backend's window
      // closes. Otherwise the user waits up to 30s for the next poll tick.
      vi.useFakeTimers({ shouldAdvanceTime: true });
      try {
        const queryClient = new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        });
        const spy = vi.spyOn(queryClient, "invalidateQueries");

        function Wrapper({ children }: { children: React.ReactNode }) {
          return React.createElement(QueryClientProvider, { client: queryClient }, children);
        }

        const { result } = renderHook(() => useSetActivePage(), { wrapper: Wrapper });

        await act(async () => {
          result.current.mutate("page-1");
        });
        await waitFor(() => expect(result.current.isSuccess).toBe(true));

        const boardKeyCalls = () =>
          spy.mock.calls.filter(([opts]) => Array.isArray(opts?.queryKey) && opts.queryKey[0] === "board-current-message");

        // Before the first scheduled tick, no board-state invalidations yet.
        expect(boardKeyCalls()).toHaveLength(0);

        // After ~750ms, the first invalidate should have fired.
        await act(async () => {
          await vi.advanceTimersByTimeAsync(800);
        });
        expect(boardKeyCalls().length).toBeGreaterThanOrEqual(1);

        // After ~3500ms total, the second (safety-net) invalidate should have fired.
        await act(async () => {
          await vi.advanceTimersByTimeAsync(3000);
        });
        expect(boardKeyCalls().length).toBeGreaterThanOrEqual(2);
      } finally {
        vi.useRealTimers();
      }
    });
  });

  describe("usePagePreview", () => {
    it("fetches preview when pageId is provided", async () => {
      const { result } = renderHook(() => usePagePreview("page-1"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.page_id).toBe("page-1");
    });

    it("is disabled when pageId is null", () => {
      const { result } = renderHook(() => usePagePreview(null), {
        wrapper: createWrapper(),
      });

      expect(result.current.fetchStatus).toBe("idle");
    });

    it("is disabled when enabled option is false", () => {
      const { result } = renderHook(() => usePagePreview("page-1", { enabled: false }), { wrapper: createWrapper() });

      expect(result.current.fetchStatus).toBe("idle");
    });
  });

  describe("useBoardSettings", () => {
    it("fetches board settings", async () => {
      const { result } = renderHook(() => useBoardSettings(), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data?.boards).toBeDefined();
    });
  });

  describe("getEffectiveBoardColor", () => {
    it("returns first board's board_color when available", () => {
      expect(
        getEffectiveBoardColor({
          board_type: "black",
          boards: [{ board_color: "white" }],
        }),
      ).toBe("white");
    });

    it("falls back to board_type when boards have no board_color", () => {
      expect(
        getEffectiveBoardColor({
          board_type: "white",
          boards: [{}],
        }),
      ).toBe("white");
    });

    it("falls back to board_type when boards array is empty", () => {
      expect(
        getEffectiveBoardColor({
          board_type: "white",
          boards: [],
        }),
      ).toBe("white");
    });

    it("falls back to board_type when boards is undefined", () => {
      expect(
        getEffectiveBoardColor({
          board_type: "white",
        }),
      ).toBe("white");
    });

    it("defaults to black when board_type is null", () => {
      expect(
        getEffectiveBoardColor({
          board_type: null,
          boards: [],
        }),
      ).toBe("black");
    });

    it("defaults to black when settings is undefined", () => {
      expect(getEffectiveBoardColor(undefined)).toBe("black");
    });
  });

  describe("getEffectiveDeviceType", () => {
    it("returns first board's device_type when it is note", () => {
      expect(
        getEffectiveDeviceType({
          boards: [{ device_type: "note" }],
        }),
      ).toBe("note");
    });

    it("returns flagship when first board is flagship", () => {
      expect(
        getEffectiveDeviceType({
          boards: [{ device_type: "flagship" }],
        }),
      ).toBe("flagship");
    });

    it("returns flagship when boards array is empty", () => {
      expect(
        getEffectiveDeviceType({
          boards: [],
        }),
      ).toBe("flagship");
    });

    it("returns flagship when boards is undefined", () => {
      expect(getEffectiveDeviceType({})).toBe("flagship");
    });

    it("defaults to flagship when settings is undefined", () => {
      expect(getEffectiveDeviceType(undefined)).toBe("flagship");
    });

    it("returns note for multi-board setup where first board is note", () => {
      expect(
        getEffectiveDeviceType({
          boards: [{ device_type: "note" }, { device_type: "flagship" }],
        }),
      ).toBe("note");
    });

    it("returns flagship when first board has no device_type", () => {
      expect(
        getEffectiveDeviceType({
          boards: [{}],
        }),
      ).toBe("flagship");
    });
  });
});

describe("use-config-overrides", () => {
  function createOverridesWrapper() {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return function Wrapper({ children }: { children: React.ReactNode }) {
      return React.createElement(
        QueryClientProvider,
        { client: queryClient },
        React.createElement(ConfigOverridesProvider, null, children),
      );
    };
  }

  it("throws when used outside provider", () => {
    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => {
      renderHook(() => useConfigOverrides());
    }).toThrow("useConfigOverrides must be used within ConfigOverridesProvider");
    consoleSpy.mockRestore();
  });

  it("starts with all overrides as null", () => {
    const { result } = renderHook(() => useConfigOverrides(), {
      wrapper: createOverridesWrapper(),
    });
    for (const key of SERVICE_KEYS) {
      expect(result.current.overrides[key]).toBeNull();
    }
  });

  it("setOverride updates a specific key", () => {
    const { result } = renderHook(() => useConfigOverrides(), {
      wrapper: createOverridesWrapper(),
    });

    act(() => {
      result.current.setOverride("weather_enabled", true);
    });

    expect(result.current.overrides.weather_enabled).toBe(true);
  });

  it("resetOverrides clears all overrides", () => {
    const { result } = renderHook(() => useConfigOverrides(), {
      wrapper: createOverridesWrapper(),
    });

    act(() => {
      result.current.setOverride("weather_enabled", true);
      result.current.setOverride("guest_wifi_enabled", false);
    });

    act(() => {
      result.current.resetOverrides();
    });

    for (const key of SERVICE_KEYS) {
      expect(result.current.overrides[key]).toBeNull();
    }
  });

  it("getEffectiveValue returns override when set", () => {
    const { result } = renderHook(() => useConfigOverrides(), {
      wrapper: createOverridesWrapper(),
    });

    act(() => {
      result.current.setOverride("weather_enabled", false);
    });

    expect(result.current.getEffectiveValue("weather_enabled", true)).toBe(false);
  });

  it("getEffectiveValue returns backend value when override is null", () => {
    const { result } = renderHook(() => useConfigOverrides(), {
      wrapper: createOverridesWrapper(),
    });

    expect(result.current.getEffectiveValue("weather_enabled", true)).toBe(true);
    expect(result.current.getEffectiveValue("weather_enabled", false)).toBe(false);
  });

  it("isOverridden returns true only for overridden keys", () => {
    const { result } = renderHook(() => useConfigOverrides(), {
      wrapper: createOverridesWrapper(),
    });

    expect(result.current.isOverridden("weather_enabled")).toBe(false);

    act(() => {
      result.current.setOverride("weather_enabled", true);
    });

    expect(result.current.isOverridden("weather_enabled")).toBe(true);
    expect(result.current.isOverridden("guest_wifi_enabled")).toBe(false);
  });

  it("getActiveOverrides returns only overridden entries", () => {
    const { result } = renderHook(() => useConfigOverrides(), {
      wrapper: createOverridesWrapper(),
    });

    act(() => {
      result.current.setOverride("weather_enabled", true);
      result.current.setOverride("guest_wifi_enabled", false);
    });

    const active = result.current.getActiveOverrides();
    expect(active).toEqual({
      weather_enabled: true,
      guest_wifi_enabled: false,
    });
  });

  it("getActiveOverrides returns empty when no overrides", () => {
    const { result } = renderHook(() => useConfigOverrides(), {
      wrapper: createOverridesWrapper(),
    });

    const active = result.current.getActiveOverrides();
    expect(active).toEqual({});
  });
});

const { mockPush, mockReplace, mockBack } = vi.hoisted(() => ({
  mockPush: vi.fn(),
  mockReplace: vi.fn(),
  mockBack: vi.fn(),
}));

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
    back: mockBack,
  }),
}));

describe("use-view-transition", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockPush.mockClear();
    mockReplace.mockClear();
    mockBack.mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  async function importUseViewTransition() {
    const mod = await import("@/hooks/use-view-transition");
    return mod.useViewTransition;
  }

  it("push navigates and sets transition class", async () => {
    const useViewTransition = await importUseViewTransition();
    const { result } = renderHook(() => useViewTransition());

    act(() => {
      result.current.push("/test", { transitionType: "slide-up" });
    });

    expect(document.documentElement.dataset.transition).toBe("slide-up");
    expect(mockPush).toHaveBeenCalledWith("/test");

    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(document.documentElement.dataset.transition).toBeUndefined();
  });

  it("push with default transition does not set class", async () => {
    const useViewTransition = await importUseViewTransition();
    const { result } = renderHook(() => useViewTransition());

    delete document.documentElement.dataset.transition;

    act(() => {
      result.current.push("/test");
    });

    expect(document.documentElement.dataset.transition).toBeUndefined();
    expect(mockPush).toHaveBeenCalledWith("/test");
  });

  it("replace navigates and sets transition class", async () => {
    const useViewTransition = await importUseViewTransition();
    const { result } = renderHook(() => useViewTransition());

    act(() => {
      result.current.replace("/other", { transitionType: "scale-fade" });
    });

    expect(document.documentElement.dataset.transition).toBe("scale-fade");
    expect(mockReplace).toHaveBeenCalledWith("/other");

    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(document.documentElement.dataset.transition).toBeUndefined();
  });

  it("back navigates with slide-down by default", async () => {
    const useViewTransition = await importUseViewTransition();
    const { result } = renderHook(() => useViewTransition());

    act(() => {
      result.current.back();
    });

    expect(document.documentElement.dataset.transition).toBe("slide-down");
    expect(mockBack).toHaveBeenCalled();

    act(() => {
      vi.advanceTimersByTime(500);
    });

    expect(document.documentElement.dataset.transition).toBeUndefined();
  });

  it("back with default transition type does not set class", async () => {
    const useViewTransition = await importUseViewTransition();
    const { result } = renderHook(() => useViewTransition());

    delete document.documentElement.dataset.transition;

    act(() => {
      result.current.back({ transitionType: "default" });
    });

    expect(document.documentElement.dataset.transition).toBeUndefined();
    expect(mockBack).toHaveBeenCalled();
  });
});
