/**
 * Keeps the IndexedDB "last known board" in step with what the app already
 * fetched (2.8, WEB-16). It reads the React Query cache, so no screen has to
 * know about it: every successful `board-current-message` poll is recorded
 * for the signed-in account, and every sign of a different (or no) account
 * wipes the store.
 */
import type { QueryCacheNotifyEvent, QueryClient } from "@tanstack/react-query";

import type { AuthStatusResponse } from "@/lib/api/auth";
import type { BoardCurrentMessageResponse, BoardSettings } from "@/lib/api/boards";

import {
  clearLastKnownBoards,
  type LastKnownBoard,
  type LastKnownBoardInfo,
  establishBoardOwner,
  readBoardSessionGeneration,
  saveLastKnownBoard,
} from "./last-known-board";

/** Re-write an unchanged frame at most this often, to refresh its time. */
export const UNCHANGED_REWRITE_MS = 60_000;

/**
 * Who the cached data belongs to. `undefined` means "can't tell yet" (no auth
 * status in the cache), and nothing is recorded until it can.
 */
export function ownerFrom(status: AuthStatusResponse | undefined): string | null | undefined {
  if (!status) return undefined;
  if (!status.enabled) return null;
  return status.authenticated && status.username ? status.username : undefined;
}

function boardInfo(settings: BoardSettings | undefined, boardId: string | null): LastKnownBoardInfo | null {
  const boards = settings?.boards ?? [];
  const board = boardId ? boards.find((b) => b.id === boardId) : boards[0];
  if (!board) return null;
  // Display settings only: never the board's address, keys or tokens.
  return {
    name: board.name,
    device_type: board.device_type,
    board_color: board.board_color,
    notes_wide: board.notes_wide ?? null,
    notes_tall: board.notes_tall ?? null,
    grid_rows: board.grid_rows ?? null,
    grid_cols: board.grid_cols ?? null,
    code62_glyph: board.code62_glyph ?? null,
    led_layout: board.led_layout ?? null,
    device_model: board.device_model ?? null,
    device_model_spec: board.device_model_spec ?? null,
  };
}

export function startLastKnownRecorder(queryClient: QueryClient, now: () => number = Date.now): () => void {
  const lastWritten = new Map<string, { message: string; at: number }>();

  let stopped = false;
  let generation: number | null = null;
  let pending = readBoardSessionGeneration().then((value) => {
    generation = value;
  });
  const enqueue = (operation: () => Promise<void>) => {
    pending = pending
      .then(async () => {
        if (!stopped) await operation();
      })
      .catch(() => {
        generation = null;
      });
  };
  const onAuthStatus = async (status: AuthStatusResponse, cached = false) => {
    if (status.enabled && (!status.authenticated || !status.username)) {
      lastWritten.clear();
      await clearLastKnownBoards();
      generation = null;
      return;
    }
    const owner = ownerFrom(status);
    if (owner === undefined || generation === null) return;
    generation = await establishBoardOwner(owner, generation, cached);
    lastWritten.clear();
  };
  const initial = queryClient.getQueryData<AuthStatusResponse>(["auth-status"]);
  if (initial) enqueue(() => onAuthStatus(initial, true));

  const onBoardMessage = async (key: readonly unknown[], data: BoardCurrentMessageResponse) => {
    if (!data || typeof data.message !== "string" || !data.rows || !data.cols) return;
    const owner = ownerFrom(queryClient.getQueryData<AuthStatusResponse>(["auth-status"]));
    if (owner === undefined || generation === null) return;
    const keyedId = typeof key[1] === "string" ? key[1] : null;
    const boardId = keyedId ?? data.board_id ?? "primary";
    const at = now();
    const previous = lastWritten.get(boardId);
    if (previous && previous.message === data.message && at - previous.at < UNCHANGED_REWRITE_MS) return;
    lastWritten.set(boardId, { message: data.message, at });
    const record: LastKnownBoard = {
      boardId,
      owner,
      message: data.message,
      ...(data.cells ? { cells: data.cells } : {}),
      rows: data.rows,
      cols: data.cols,
      board: boardInfo(queryClient.getQueryData<BoardSettings>(["boardSettings"]), keyedId ?? data.board_id ?? null),
      savedAt: at,
    };
    await saveLastKnownBoard(record, generation);
  };

  const boardRequests = new Map<string, { owner: string | null | undefined; generation: Promise<number> }>();
  const unsubscribe = queryClient.getQueryCache().subscribe((event: QueryCacheNotifyEvent) => {
    if (event.type !== "updated") return;
    const key = event.query.queryKey;
    if (key[0] === "auth-status" && event.action.type === "fetch") {
      // A new verification can resume after sign-out; an already in-flight response cannot.
      const freshGeneration = readBoardSessionGeneration();
      enqueue(async () => {
        generation = await freshGeneration;
      });
    }
    if (key[0] === "board-current-message" && event.action.type === "fetch") {
      boardRequests.set(event.query.queryHash, {
        owner: ownerFrom(queryClient.getQueryData<AuthStatusResponse>(["auth-status"])),
        generation: readBoardSessionGeneration(),
      });
    }
    if (event.action.type !== "success") return;
    const data = event.action.data;
    if (key[0] === "auth-status") enqueue(() => onAuthStatus(data as AuthStatusResponse));
    else if (key[0] === "board-current-message") {
      const request = boardRequests.get(event.query.queryHash);
      const eventOwner = ownerFrom(queryClient.getQueryData<AuthStatusResponse>(["auth-status"]));
      enqueue(async () => {
        if (eventOwner !== ownerFrom(queryClient.getQueryData<AuthStatusResponse>(["auth-status"]))) return;
        if (request && (request.owner !== eventOwner || (await request.generation) !== generation)) return;
        await onBoardMessage(key, data as BoardCurrentMessageResponse);
      });
    }
  });
  return () => {
    stopped = true;
    unsubscribe();
  };
}
