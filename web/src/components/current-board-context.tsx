"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";

import { useBoardSettings } from "@/hooks/use-board";
import type { BoardInstance } from "@/lib/api";

const STORAGE_KEY = "fiestaboard_current_board";

type BoardSwitchDirection = "forward" | "backward";

/** Minimal typing for the View Transitions API (not yet in lib.dom). */
interface DocumentWithViewTransition extends Document {
  startViewTransition?: (update: () => void) => { finished: Promise<void> };
}

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
 */
function runBoardSwitchTransition(direction: BoardSwitchDirection, update: () => void) {
  const doc = document as DocumentWithViewTransition;
  if (typeof doc.startViewTransition !== "function" || motionDisabled()) {
    update();
    return;
  }
  doc.documentElement.dataset.boardSwitch = direction;
  const transition = doc.startViewTransition(() => {
    // The browser snapshots "old" before and "new" after this callback, so the
    // React commit must land synchronously inside it.
    flushSync(update);
  });
  transition.finished.finally(() => {
    delete doc.documentElement.dataset.boardSwitch;
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
  useEffect(() => {
    if (boards.length === 0) return;
    const primaryId = boards[0].id;

    setCurrentBoardIdState((prev) => {
      // Prefer the in-memory selection if it's still valid.
      if (prev && boards.some((b) => b.id === prev)) return prev;

      const stored = readStoredBoardId();
      if (stored && boards.some((b) => b.id === stored)) return stored;

      return primaryId;
    });
  }, [boards]);

  // Refs so setCurrentBoardId can compute the switch direction without
  // changing identity every time the selection or board list updates.
  const currentBoardIdRef = useRef(currentBoardId);
  const boardsRef = useRef(boards);
  useEffect(() => {
    currentBoardIdRef.current = currentBoardId;
  }, [currentBoardId]);
  useEffect(() => {
    boardsRef.current = boards;
  }, [boards]);

  const setCurrentBoardId = useCallback((boardId: string) => {
    if (boardId === currentBoardIdRef.current) return;

    // Moving down the board list slides forward; moving up slides backward —
    // mirrors the order the user sees in the sidebar selector.
    const list = boardsRef.current;
    const fromIndex = list.findIndex((b) => b.id === currentBoardIdRef.current);
    const toIndex = list.findIndex((b) => b.id === boardId);
    const direction: BoardSwitchDirection = toIndex >= fromIndex ? "forward" : "backward";

    runBoardSwitchTransition(direction, () => {
      setCurrentBoardIdState(boardId);
    });
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
