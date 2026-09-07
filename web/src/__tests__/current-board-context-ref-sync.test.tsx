import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider, useCurrentBoard } from "@/components/current-board-context";

import { server } from "./mocks/server";

const API_BASE = "/api";

function Probe() {
  const { currentBoardId, setCurrentBoardId } = useCurrentBoard();
  return (
    <div>
      <span data-testid="current-id">{currentBoardId}</span>
      <button data-testid="select-one" onClick={() => setCurrentBoardId("one")} />
    </div>
  );
}

function renderProbe() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <CurrentBoardProvider>
        <Probe />
      </CurrentBoardProvider>
    </QueryClientProvider>,
  );
}

/**
 * `CurrentBoardProvider` mirrors `currentBoardId` into a ref so `setCurrentBoardId`
 * can compare against it without the callback changing identity on every
 * selection. The sync has to happen in a LAYOUT effect, and nothing in the
 * suite covered that until now.
 *
 * With a passive effect, React defers the sync until after paint. That leaves a
 * window where the committed DOM already shows the reconciled board but the ref
 * still holds the previous value — so a click landing in it compares against a
 * stale id and starts a view transition to the board the user is already on.
 *
 * The window is real but narrow, so polling for it with `waitFor` only catches
 * it intermittently. A MutationObserver closes it deterministically: its
 * callback is a microtask, so it runs after the commit that paints the board
 * but before React's scheduler gets the macrotask in which it would flush
 * passive effects. Clicking from there lands exactly inside the window.
 */
describe("CurrentBoardProvider — ref sync timing", () => {
  let startViewTransition: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    localStorage.clear();
    startViewTransition = vi.fn((cb: () => void) => {
      cb();
      return { finished: Promise.resolve() };
    });
    (document as unknown as { startViewTransition: unknown }).startViewTransition = startViewTransition;
    server.use(
      http.get(`${API_BASE}/settings/board`, () =>
        HttpResponse.json({
          board_type: "black",
          boards: [
            { id: "one", name: "Kitchen", device_type: "flagship", board_color: "black" },
            { id: "two", name: "Office", device_type: "flagship", board_color: "black" },
          ],
          devices: ["flagship"],
        }),
      ),
    );
  });

  afterEach(() => {
    delete (document as unknown as { startViewTransition?: unknown }).startViewTransition;
    delete document.documentElement.dataset.boardSwitch;
  });

  it("does not start a transition for a click landing in the same commit that paints the board", async () => {
    let clicked = false;
    const observer = new MutationObserver(() => {
      if (clicked) return;
      const current = document.querySelector('[data-testid="current-id"]');
      if (current?.textContent !== "one") return;
      clicked = true;
      (document.querySelector('[data-testid="select-one"]') as HTMLElement).click();
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true });

    try {
      renderProbe();
      await waitFor(() => expect(clicked).toBe(true));
    } finally {
      observer.disconnect();
    }

    // The click selected the board that was already current, so the guard in
    // setCurrentBoardId must have seen an up-to-date ref and bailed out.
    expect(startViewTransition).not.toHaveBeenCalled();
  });
});
