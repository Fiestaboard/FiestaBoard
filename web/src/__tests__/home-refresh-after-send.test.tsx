import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useRefreshHomeStatus } from "@/components/home/use-home-data";

// BB-A-1: after Show now (Compose, Change Page) the first refetch of what the
// board shows races the display's own write, and the 30 s poll then left the
// Home preview on the old page. The refresh must ask again once the write has
// landed (the backend's post-send window closes within ~3 s).
describe("useRefreshHomeStatus (BB-A-1)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function boardMessageInvalidations(spy: { mock: { calls: unknown[][] } }) {
    return spy.mock.calls.filter(([filters]) => {
      const key = (filters as { queryKey?: readonly unknown[] } | undefined)?.queryKey;
      return Array.isArray(key) && key[0] === "board-current-message";
    }).length;
  }

  it("re-reads the board after the send has had time to land, not only at once", () => {
    const queryClient = new QueryClient();
    const spy = vi.spyOn(queryClient, "invalidateQueries");
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useRefreshHomeStatus(), { wrapper });

    result.current();
    expect(boardMessageInvalidations(spy)).toBe(1);

    vi.advanceTimersByTime(1000);
    expect(boardMessageInvalidations(spy)).toBe(2);

    vi.advanceTimersByTime(3000);
    expect(boardMessageInvalidations(spy)).toBe(3);
  });
});
