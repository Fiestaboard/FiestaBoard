/**
 * A display's live preview on /displays (plan D21) must sit still when there
 * is nothing new to show.
 *
 * Reported: a paused Vestaboard, unplugged in a box, spun its flaps on the
 * Displays page over and over. Its board-state read failed (503), and every
 * 30 s poll of a query that never succeeded went back to "pending" — which
 * the preview drew as the loading animation, for as long as each failing
 * read took. A paused board should not be polled at all, and an unreachable
 * one must settle into a static state instead of looping the animation.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DisplayLivePreview } from "@/components/displays/display-live-preview";
import type { BoardInstance } from "@/lib/api";

import { server } from "./mocks/server";

const API = "/api";
const LOADING = "Loading board display";

const BOARD = {
  id: "kitchen",
  name: "Kitchen",
  device_type: "flagship",
  board_color: "black",
  output: "vestaboard",
  output_config: { api_mode: "local", host: "192.0.2.10" },
} as unknown as BoardInstance;

const FRAME = {
  characters: [[8, 9]],
  message: "HI",
  rows: 1,
  cols: 2,
  expected_characters: null,
  cached_at: null,
  api_mode: "local",
};

/** Serve the board-state read; `respond` decides each answer. Returns the request count. */
function serveBoardState(respond: (n: number) => Promise<Response> | Response) {
  const calls = { count: 0 };
  server.use(
    http.get(`${API}/board/current-message`, () => {
      calls.count += 1;
      return respond(calls.count);
    }),
  );
  return calls;
}

function renderPreview(board: BoardInstance) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <DisplayLivePreview board={board} />
    </QueryClientProvider>,
  );
  return client;
}

afterEach(() => {
  vi.useRealTimers();
});

describe("DisplayLivePreview", () => {
  it("does not replay the loading animation when an unreachable board is polled again", async () => {
    let release: () => void = () => {};
    const calls = serveBoardState((n) =>
      n === 1
        ? HttpResponse.json({ detail: "Failed to read current board message" }, { status: 503 })
        : new Promise<Response>((resolve) => {
            release = () => resolve(HttpResponse.json({ detail: "unreachable" }, { status: 503 }));
          }),
    );
    const client = renderPreview(BOARD);

    // The first read fails: the preview settles on a static board.
    await waitFor(() => expect(calls.count).toBe(1));
    await waitFor(() => expect(screen.queryByLabelText(LOADING)).toBeNull());

    // The next poll is in flight (a read of an unplugged board can hang).
    act(() => {
      void client.refetchQueries();
    });
    await waitFor(() => expect(calls.count).toBe(2));

    expect(screen.queryByLabelText(LOADING)).toBeNull();
    release();
  });

  it("never draws a paused board as loading", async () => {
    let release: () => void = () => {};
    const calls = serveBoardState(
      () =>
        new Promise<Response>((resolve) => {
          release = () => resolve(HttpResponse.json(FRAME));
        }),
    );
    renderPreview({ ...BOARD, paused: true });

    await waitFor(() => expect(calls.count).toBe(1));

    expect(screen.queryByLabelText(LOADING)).toBeNull();
    release();
  });

  it("does not poll a paused board", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    const calls = serveBoardState(() => HttpResponse.json(FRAME));
    renderPreview({ ...BOARD, paused: true });

    await act(() => vi.advanceTimersByTimeAsync(100));
    expect(calls.count).toBe(1);

    await act(() => vi.advanceTimersByTimeAsync(95_000));
    expect(calls.count).toBe(1);
  });

  it("keeps polling a board that is not paused", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "setInterval", "clearInterval"] });
    const calls = serveBoardState(() => HttpResponse.json(FRAME));
    renderPreview(BOARD);

    await act(() => vi.advanceTimersByTimeAsync(100));
    expect(calls.count).toBe(1);

    await act(() => vi.advanceTimersByTimeAsync(95_000));
    expect(calls.count).toBeGreaterThan(1);
  });
});
