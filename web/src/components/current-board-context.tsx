"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";

import { useBoardSettings } from "@/hooks/use-board";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import type { BoardInstance } from "@/lib/api";

const STORAGE_KEY = "fiestaboard_current_board";

type BoardSwitchDirection = "forward" | "backward";

function motionDisabled(): boolean {
  const html = document.documentElement;
  if (html.classList.contains("reduce-motion") || html.classList.contains("site-animations-off")) return true;
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

/**
 * Run `update` inside a directional view transition so switching boards reads
 * as a SWITCH: the old page slides out one way, the new page slides in from
 * the other (CSS in globals.css keys off `html[data-board-switch]`). Falls
 * back to an instant switch when the View Transitions API is unavailable or
 * the user prefers reduced motion.
 *
 * `onSettled` runs once the transition finishes OR is aborted, and on the
 * instant-switch path runs immediately.
 */
function runBoardSwitchTransition(direction: BoardSwitchDirection, update: () => void, onSettled: () => void) {
  const doc = document;
  // lib.dom declares startViewTransition unconditionally; browsers that predate
  // the View Transitions API (and jsdom) still don't ship it, so probe at runtime.
  if (typeof doc.startViewTransition !== "function" || motionDisabled()) {
    update();
    onSettled();
    return;
  }
  doc.documentElement.dataset.boardSwitch = direction;
  const transition = doc.startViewTransition(() => {
    // The browser snapshots "old" before and "new" after this callback, so the
    // React commit must land synchronously inside it.
    flushSync(update);
  });
  transition.finished
    // A transition started while another is active SKIPS the earlier one and
    // rejects its `finished` with AbortError. That is a normal outcome of a
    // fast second switch, not an error — but `.finally()` re-raises a rejection
    // on the promise it returns, so without this `.catch()` every abort leaks
    // an unhandled rejection.
    .catch(() => {})
    .finally(() => {
      delete doc.documentElement.dataset.boardSwitch;
      onSettled();
    });
}

interface CurrentBoardContextValue {
  /** ID of the board the user is currently managing. Empty string until boards load. */
  currentBoardId: string;
  /** Select a board to manage; persists the choice to localStorage. */
  setCurrentBoardId: (boardId: string) => void;
  /** The resolved board instance for `currentBoardId`, or undefined while loading. */
  currentBoard: BoardInstance | undefined;
  /** The live list of board instances from board settings. */
  boards: BoardInstance[];
}

const CurrentBoardContext = createContext<CurrentBoardContextValue>({
  currentBoardId: "",
  setCurrentBoardId: () => {},
  currentBoard: undefined,
  boards: [],
});

function readStoredBoardId(): string | null {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function CurrentBoardProvider({ children }: { children: React.ReactNode }) {
  const { data: boardSettings } = useBoardSettings();

  // Memoize so the boards array identity is stable between renders when the
  // query data is unchanged; downstream effects depend on it.
  const boards = useMemo(() => boardSettings?.boards ?? [], [boardSettings?.boards]);

  const [currentBoardId, setCurrentBoardIdState] = useState<string>("");

  // Reconcile the selected board against the live board list. The default is
  // the PRIMARY board (boards[0]); a stored id is honored only if it still
  // maps to an existing board, otherwise it's dropped in favor of the primary.
  //
  // Done during render rather than in an effect (react-hooks/set-state-in-effect,
  // issue #1568): the reconciled id is then in the same commit as the board
  // list it was reconciled against, so consumers never see the empty-string
  // placeholder alongside a populated `boards`.
  if (useDepsChanged([boards]) && boards.length > 0) {
    const primaryId = boards[0].id;

    setCurrentBoardIdState((prev) => {
      // Prefer the in-memory selection if it's still valid.
      if (prev && boards.some((b) => b.id === prev)) return prev;

      const stored = readStoredBoardId();
      if (stored && boards.some((b) => b.id === stored)) return stored;

      return primaryId;
    });
  }

  // Refs so setCurrentBoardId can compute the switch direction without
  // changing identity every time the selection or board list updates.
  //
  // These sync in a LAYOUT effect, not a passive one: passive effects are
  // deferred until after paint, which leaves a window where the committed DOM
  // already shows the reconciled board but the refs still hold the previous
  // value. A click landing in that window makes setCurrentBoardId compare
  // against a stale id — re-selecting the board that is already current would
  // run a spurious view transition, and a real switch would compute its
  // direction from the wrong `fromIndex`. Layout effects run synchronously
  // with the commit, so the refs can never lag what the user sees.
  const currentBoardIdRef = useRef(currentBoardId);
  const boardsRef = useRef(boards);
  useLayoutEffect(() => {
    currentBoardIdRef.current = currentBoardId;
  }, [currentBoardId]);
  useLayoutEffect(() => {
    boardsRef.current = boards;
  }, [boards]);

  // The board a transition is currently heading toward, or "" when none is in
  // flight. `startViewTransition` invokes its callback asynchronously, so
  // `setCurrentBoardIdState` — and therefore `currentBoardIdRef` — has not
  // moved yet while a switch is in flight. Recording the target synchronously,
  // with no commit required, is what lets the guard below see it.
  const pendingIdRef = useRef("");

  const setCurrentBoardId = useCallback((boardId: string) => {
    if (boardId === (pendingIdRef.current || currentBoardIdRef.current)) return;
    pendingIdRef.current = boardId;

    // Moving down the board list slides forward; moving up slides backward —
    // mirrors the order the user sees in the sidebar selector.
    const list = boardsRef.current;
    const fromIndex = list.findIndex((b) => b.id === currentBoardIdRef.current);
    const toIndex = list.findIndex((b) => b.id === boardId);
    const direction: BoardSwitchDirection = toIndex >= fromIndex ? "forward" : "backward";

    runBoardSwitchTransition(
      direction,
      () => {
        setCurrentBoardIdState(boardId);
      },
      () => {
        // Only clear if a newer switch has not already claimed the slot —
        // otherwise an earlier transition aborting would drop the guard for the
        // switch that superseded it.
        if (pendingIdRef.current === boardId) pendingIdRef.current = "";
      },
    );
    try {
      localStorage.setItem(STORAGE_KEY, boardId);
    } catch {}
  }, []);

  const currentBoard = useMemo(() => boards.find((b) => b.id === currentBoardId), [boards, currentBoardId]);

  const value = useMemo(
    () => ({ currentBoardId, setCurrentBoardId, currentBoard, boards }),
    [currentBoardId, setCurrentBoardId, currentBoard, boards],
  );

  return <CurrentBoardContext.Provider value={value}>{children}</CurrentBoardContext.Provider>;
}

export function useCurrentBoard() {
  return useContext(CurrentBoardContext);
}
