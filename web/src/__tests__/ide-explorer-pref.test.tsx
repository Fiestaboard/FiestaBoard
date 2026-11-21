/**
 * Owner decision D2 (BB-E-3): the Explorer opens by default for multi-board
 * (Note array) and big-board (FiestaPanel) pages and starts closed for a
 * single Flagship or Note; the reader's toggle is remembered per board kind.
 */
import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { explorerOpenByDefault, useExplorerOpen } from "@/lib/ide/explorer-pref";

beforeEach(() => localStorage.clear());

describe("explorerOpenByDefault", () => {
  it.each([
    ["flagship", false],
    ["note", false],
    ["note_array", true],
    ["panel", true],
  ] as const)("%s → %s", (kind, open) => {
    expect(explorerOpenByDefault(kind)).toBe(open);
  });
});

describe("useExplorerOpen", () => {
  it("follows the default for a kind the reader has not toggled", () => {
    expect(renderHook(() => useExplorerOpen("flagship")).result.current[0]).toBe(false);
    expect(renderHook(() => useExplorerOpen("panel")).result.current[0]).toBe(true);
  });

  it("remembers the reader's toggle for that kind only", () => {
    const { result } = renderHook(() => useExplorerOpen("flagship"));
    act(() => result.current[1](true));
    expect(result.current[0]).toBe(true);
    expect(localStorage.getItem("fiestaboard_ide_explorer:flagship")).toBe("open");
    expect(renderHook(() => useExplorerOpen("flagship")).result.current[0]).toBe(true);
    expect(renderHook(() => useExplorerOpen("note")).result.current[0]).toBe(false);
  });

  it("remembers closing it for a kind that opens by default", () => {
    const { result } = renderHook(() => useExplorerOpen("note_array"));
    act(() => result.current[1](false));
    expect(localStorage.getItem("fiestaboard_ide_explorer:note_array")).toBe("closed");
    expect(renderHook(() => useExplorerOpen("note_array")).result.current[0]).toBe(false);
  });

  it("switches to the other kind's choice when the editor moves to a page of another kind", () => {
    localStorage.setItem("fiestaboard_ide_explorer:panel", "closed");
    const { result, rerender } = renderHook(({ kind }) => useExplorerOpen(kind), {
      initialProps: { kind: "flagship" as "flagship" | "panel" },
    });
    act(() => result.current[1](true));
    rerender({ kind: "panel" });
    expect(result.current[0]).toBe(false);
    rerender({ kind: "flagship" });
    expect(result.current[0]).toBe(true);
  });

  it("falls back to the default when storage is unavailable", () => {
    const original = Storage.prototype.getItem;
    Storage.prototype.getItem = () => {
      throw new Error("blocked");
    };
    try {
      expect(renderHook(() => useExplorerOpen("panel")).result.current[0]).toBe(true);
    } finally {
      Storage.prototype.getItem = original;
    }
  });
});
