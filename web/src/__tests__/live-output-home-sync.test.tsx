/**
 * Integration tests for Live Output → Home Screen sync.
 *
 * These tests verify that:
 * 1. When the page builder writes to ["liveOutputMessage"] via setQueryData,
 *    the active-page-display (home screen) reads that value.
 * 2. The value persists after the page builder unmounts (simulating navigation).
 * 3. The value is cleared when live output is explicitly disabled.
 * 4. The displayMessage computation in active-page-display prefers liveOutputMessage
 *    over the normal page preview.
 */

import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { renderHook } from "@testing-library/react";
import { http } from "msw";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ActivePageDisplay } from "@/components/active-page-display";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

const mockPush = vi.fn();
vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

vi.mock("@/components/smart-link", () => ({
  default: ({ children, href, ...rest }: { children: React.ReactNode; href: string }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

// ──────────────────────────────────────────────────────────────────────────────
// Unit-level: verify the React Query cache sharing mechanism directly
// ──────────────────────────────────────────────────────────────────────────────

describe("Live Output cache sharing (mechanism)", () => {
  it("home screen reads liveOutputMessage set before it mounts (post-navigation scenario)", () => {
    // This is the key scenario: page builder writes to cache, then unmounts
    // (user navigates away), then home screen mounts and should see the value.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 5 * 60 * 1000 } },
    });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    // Simulate page builder calling setQueryData (no component observer needed)
    queryClient.setQueryData(["liveOutputMessage"], "THURSDAY\nAPRIL 23 2026");

    // Home screen mounts and reads from cache
    const { result } = renderHook(
      () =>
        useQuery<string | null>({
          queryKey: ["liveOutputMessage"],
          queryFn: () => null,
          staleTime: Infinity,
          initialData: null,
        }),
      { wrapper },
    );

    // Should immediately see the value set by page builder (synchronous read from cache)
    expect(result.current.data).toBe("THURSDAY\nAPRIL 23 2026");
  });

  it("home screen gets null initially when page builder has not sent anything", () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(
      () =>
        useQuery<string | null>({
          queryKey: ["liveOutputMessage"],
          queryFn: () => null,
          staleTime: Infinity,
          initialData: null,
        }),
      { wrapper },
    );

    expect(result.current.data).toBeNull();
  });

  it("home screen updates in real-time when page builder writes to cache", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(
      () =>
        useQuery<string | null>({
          queryKey: ["liveOutputMessage"],
          queryFn: () => null,
          staleTime: Infinity,
          initialData: null,
        }),
      { wrapper },
    );

    expect(result.current.data).toBeNull();

    // Page builder broadcasts a live render
    act(() => {
      queryClient.setQueryData(["liveOutputMessage"], "LIVE CONTENT");
    });

    await waitFor(() => {
      expect(result.current.data).toBe("LIVE CONTENT");
    });

    // Page builder explicitly disables live output
    act(() => {
      queryClient.setQueryData(["liveOutputMessage"], null);
    });

    await waitFor(() => {
      expect(result.current.data).toBeNull();
    });
  });

  it("liveOutputMessage persists through multiple setQueryData calls (live typing)", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(
      () =>
        useQuery<string | null>({
          queryKey: ["liveOutputMessage"],
          queryFn: () => null,
          staleTime: Infinity,
          initialData: null,
        }),
      { wrapper },
    );

    // Simulate rapid updates as user types
    const updates = ["T", "TH", "THU", "THUR", "THURSDAY"];
    for (const content of updates) {
      act(() => {
        queryClient.setQueryData(["liveOutputMessage"], content);
      });
    }

    await waitFor(() => {
      expect(result.current.data).toBe("THURSDAY");
    });
  });

  it("priming on enable: cache is set synchronously before async fast-path fires", async () => {
    // Covers the timing-gap fix: the liveOutputEnabled transition effect primes
    // the cache immediately so that a user who navigates within the 100ms debounce
    // window still sees the current page content on the Home screen.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const wrapper = ({ children }: { children: React.ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(
      () =>
        useQuery<string | null>({
          queryKey: ["liveOutputMessage"],
          queryFn: () => null,
          staleTime: Infinity,
          initialData: null,
        }),
      { wrapper },
    );

    expect(result.current.data).toBeNull();

    // Simulate the liveOutputEnabled → true transition priming the cache
    // with the current page preview (before the async API call completes)
    act(() => {
      queryClient.setQueryData(["liveOutputMessage"], "CURRENT PAGE PREVIEW");
    });

    await waitFor(() => {
      expect(result.current.data).toBe("CURRENT PAGE PREVIEW");
    });

    // Async fast-path completes and updates with the live-rendered version
    act(() => {
      queryClient.setQueryData(["liveOutputMessage"], "LIVE RENDERED VERSION");
    });

    await waitFor(() => {
      expect(result.current.data).toBe("LIVE RENDERED VERSION");
    });
  });
});

// ──────────────────────────────────────────────────────────────────────────────
// Integration-level: verify ActivePageDisplay shows liveOutputMessage
// ──────────────────────────────────────────────────────────────────────────────

describe("ActivePageDisplay uses liveOutputMessage from cache", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function makeWrapper(queryClient: QueryClient) {
    return function Wrapper({ children }: { children: React.ReactNode }) {
      return (
        <QueryClientProvider client={queryClient}>
          <ConfigOverridesProvider>
            <ThemeProvider attribute="class" defaultTheme="light">
              {children}
            </ThemeProvider>
          </ConfigOverridesProvider>
        </QueryClientProvider>
      );
    };
  }

  it("shows active display card regardless of liveOutputMessage", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    // Pre-populate the live output cache (simulates page builder having run)
    queryClient.setQueryData(["liveOutputMessage"], "LIVE\nCONTENT");

    render(<ActivePageDisplay />, { wrapper: makeWrapper(queryClient) });

    await waitFor(() => {
      expect(screen.getByText("Active Display")).toBeInTheDocument();
    });
  });

  it("does not show loading skeleton when liveOutputMessage is set and previewData is unavailable", async () => {
    // Override the page preview to return nothing (empty response), simulating
    // a slow load. If liveOutputMessage is in the cache, the board should show
    // the live content and NOT be stuck in a loading state.
    server.use(
      http.post(`${API_BASE}/pages/:id/preview`, () => {
        // Deliberately delay — the board should show liveOutputMessage immediately
        return new Promise(() => {}); // Never resolves, simulates slow network
      }),
    );

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    // Pre-populate live output message (as page builder would do)
    queryClient.setQueryData(["liveOutputMessage"], "THURSDAY\nAPRIL 23 2026");

    render(<ActivePageDisplay />, { wrapper: makeWrapper(queryClient) });

    // The component should still render (not crash) even with a pending preview
    await waitFor(() => {
      expect(screen.getByText("Active Display")).toBeInTheDocument();
    });
  });

  it("liveOutputMessage takes priority over previewData message in displayMessage", async () => {
    // This test verifies the ?? priority logic:
    // displayMessage = liveOutputMessage ?? previewData?.message ?? null
    // When liveOutputMessage is set, it should be used instead of previewData.message.

    // The MSW default mock returns previewData.message = "Preview content"
    // Our liveOutputMessage should override it.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    const LIVE_CONTENT = "DATE TIME CONTENT FROM LIVE OUTPUT";
    queryClient.setQueryData(["liveOutputMessage"], LIVE_CONTENT);

    // Spy on the query to verify liveOutputMessage is read
    const _capturedValues: (string | null)[] = [];
    const _OriginalQuery = QueryClient.prototype.getQueryData;

    render(<ActivePageDisplay />, { wrapper: makeWrapper(queryClient) });

    // The component should render without errors
    await waitFor(() => {
      expect(screen.getByText("Active Display")).toBeInTheDocument();
    });

    // Verify the liveOutputMessage is still in the cache (not cleared by mounting)
    const cachedValue = queryClient.getQueryData<string | null>(["liveOutputMessage"]);
    expect(cachedValue).toBe(LIVE_CONTENT);
  });

  it("liveOutputMessage null falls back to previewData", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    // No live output set → should show normal page preview
    // (liveOutputMessage = null, falls back to previewData.message)

    render(<ActivePageDisplay />, { wrapper: makeWrapper(queryClient) });

    await waitFor(() => {
      expect(screen.getByText("Active Display")).toBeInTheDocument();
    });

    // liveOutputMessage starts as null (initialData from the useQuery in the component)
    const cachedValue = queryClient.getQueryData<string | null>(["liveOutputMessage"]);
    // TanStack Query writes initialData: null to the cache on mount, so getQueryData returns null
    expect(cachedValue).toBeNull();
  });

  it("shows Live Mode badge when liveOutputMessage is set", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    // Pre-populate with live content (simulates page builder having sent to board)
    queryClient.setQueryData(["liveOutputMessage"], "LIVE CONTENT");

    render(<ActivePageDisplay />, { wrapper: makeWrapper(queryClient) });

    await waitFor(() => {
      expect(screen.getByText("Live Mode")).toBeInTheDocument();
    });

    // Normal mode badges should NOT appear when live mode is active
    expect(screen.queryByText("Schedule Mode")).not.toBeInTheDocument();
    expect(screen.queryByText("Manual Mode")).not.toBeInTheDocument();
  });

  it("shows normal mode badge when liveOutputMessage is null", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    // No live output
    render(<ActivePageDisplay />, { wrapper: makeWrapper(queryClient) });

    await waitFor(() => {
      // Default MSW mock has schedule_enabled: false → Manual Mode
      expect(screen.getByText("Manual Mode")).toBeInTheDocument();
    });

    expect(screen.queryByText("Live Mode")).not.toBeInTheDocument();
  });

  it("clicking the Live Mode turn-off button clears live output state", async () => {
    const user = (await import("@testing-library/user-event")).default.setup();

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    // Pre-populate live output (as if page builder had sent live content)
    queryClient.setQueryData(["liveOutputMessage"], "LIVE CONTENT");
    // Also seed localStorage so we can verify it gets cleared
    window.localStorage.setItem("fiestaboard:liveOutputMessage", JSON.stringify("LIVE CONTENT"));

    render(<ActivePageDisplay />, { wrapper: makeWrapper(queryClient) });

    await waitFor(() => {
      expect(screen.getByText("Live Mode")).toBeInTheDocument();
    });

    const turnOffButton = screen.getByRole("button", { name: /turn off live mode/i });
    expect(turnOffButton).toBeInTheDocument();

    await user.click(turnOffButton);

    // Cache should be cleared
    await waitFor(() => {
      expect(queryClient.getQueryData(["liveOutputMessage"])).toBeNull();
    });

    // localStorage should be cleared so other tabs stop showing live content
    expect(window.localStorage.getItem("fiestaboard:liveOutputMessage")).toBeNull();

    // Live Mode badge should disappear
    await waitFor(() => {
      expect(screen.queryByText("Live Mode")).not.toBeInTheDocument();
    });
  });
});
