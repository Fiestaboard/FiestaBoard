// useSetActivePage takes a page id OR { pageId, overrideSilence } (#1943).
// Every existing `mutate(pageId)` caller keeps sending exactly the body it
// always sent; only an explicit override adds `override_silence: true`.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createElement, type ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { queryKeys, useSetActivePage } from "@/hooks/use-board";

import { server } from "./mocks/server";

const API_BASE = "/api";

function setup(boardId?: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => createElement(QueryClientProvider, { client }, children);
  const hook = renderHook(() => useSetActivePage(boardId), { wrapper });
  return { client, ...hook };
}

function captureBodies(status = 200) {
  const bodies: Record<string, unknown>[] = [];
  server.use(
    http.put(`${API_BASE}/settings/active-page`, async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      bodies.push(body);
      if (status !== 200) return HttpResponse.json({ detail: "nope" }, { status });
      return HttpResponse.json({
        page_id: body.page_id,
        sent_to_board: false,
        paused: false,
        silenced: true,
        board_id: body.board_id ?? null,
        error: null,
        warnings: [],
      });
    }),
  );
  return bodies;
}

describe("useSetActivePage", () => {
  afterEach(() => server.resetHandlers());

  it("a bare page id sends no override_silence", async () => {
    const bodies = captureBodies();
    const { result } = setup();
    await act(() => result.current.mutateAsync("page-2"));
    expect(bodies).toEqual([{ page_id: "page-2" }]);
  });

  it("{ pageId, overrideSilence: true } sends override_silence and the board", async () => {
    const bodies = captureBodies();
    const { result } = setup("b2");
    const response = await act(() => result.current.mutateAsync({ pageId: "page-2", overrideSilence: true }));
    expect(bodies).toEqual([{ page_id: "page-2", board_id: "b2", override_silence: true }]);
    expect(response.silenced).toBe(true);
  });

  it("{ pageId } without the flag is the same as a bare id", async () => {
    const bodies = captureBodies();
    const { result } = setup();
    await act(() => result.current.mutateAsync({ pageId: null }));
    expect(bodies).toEqual([{ page_id: null }]);
  });

  it("updates the active page optimistically from either form", async () => {
    let release: () => void = () => {};
    server.use(
      http.put(`${API_BASE}/settings/active-page`, async () => {
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        return HttpResponse.json({ page_id: "page-2", sent_to_board: true, paused: false, silenced: false });
      }),
    );
    const { client, result } = setup();
    client.setQueryData(queryKeys.activePage(undefined), { page_id: "page-1" });
    act(() => {
      result.current.mutate({ pageId: "page-2", overrideSilence: true });
    });
    await waitFor(() => expect(client.getQueryData(queryKeys.activePage(undefined))).toEqual({ page_id: "page-2" }));
    release();
  });

  it("rolls back on failure", async () => {
    captureBodies(500);
    const { client, result } = setup();
    client.setQueryData(queryKeys.activePage(undefined), { page_id: "page-1" });
    await act(async () => {
      await result.current.mutateAsync({ pageId: "page-2", overrideSilence: true }).catch(() => {});
    });
    expect(client.getQueryData(queryKeys.activePage(undefined))).toEqual({ page_id: "page-1" });
  });
});
