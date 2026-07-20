"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { useBoardSettings } from "@/hooks/use-board";
import type { BoardInstance } from "@/lib/api";

const STORAGE_KEY = "fiestaboard_current_board";

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

  const setCurrentBoardId = useCallback((boardId: string) => {
    setCurrentBoardIdState(boardId);
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
