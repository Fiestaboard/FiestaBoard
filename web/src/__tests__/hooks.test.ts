import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import React from "react";
import { describe, expect, it } from "vitest";

import { useActivePage, useConfig, usePages, useStatus } from "@/hooks/use-board";

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
