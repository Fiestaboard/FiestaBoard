import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";

import { collectionPollMs, useActivePage, useConfig, usePages, useStatus } from "@/hooks/use-board";

// Wrapper for react-query
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

describe("useStatus", () => {
  it("fetches status from API", async () => {
    const { result } = renderHook(() => useStatus(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.running).toBe(true);
  });
});

describe("useConfig", () => {
  it("fetches config from API", async () => {
    const { result } = renderHook(() => useConfig(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.weather_enabled).toBe(true);
    expect(result.current.data?.home_assistant_enabled).toBe(false);
  });
});

describe("useActivePage", () => {
  it("fetches active page from API", async () => {
    const { result } = renderHook(() => useActivePage(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // Active page may or may not be set
    expect(result.current.data).toHaveProperty("page_id");
  });
});

describe("usePages", () => {
  it("fetches pages list from API", async () => {
    const { result } = renderHook(() => usePages(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveProperty("pages");
    expect(Array.isArray(result.current.data?.pages)).toBe(true);
  });
});

// Issue #1513: the Dashboard names the member page a collection is currently
// rendering, so it has to re-poll on the collection's cadence rather than
// caching a name that goes wrong within seconds.
describe("collectionPollMs", () => {
  it("does not poll when the active reference cannot rotate", () => {
    // Plain pages (and single-page collections) report null.
    expect(collectionPollMs(null)).toBe(false);
    expect(collectionPollMs(undefined)).toBe(false);
  });

  it("polls on the collection's own cadence", () => {
    expect(collectionPollMs(30)).toBe(30000);
    expect(collectionPollMs(5)).toBe(5000);
  });

  it("floors a near-instant boundary so it cannot become a tight loop", () => {
    expect(collectionPollMs(1)).toBe(2000);
    expect(collectionPollMs(0)).toBe(2000);
  });
});
