import { useCallback, useState } from "react";

import type { DeviceType } from "@/lib/api";

/**
 * Owner decision D2 (BB-E-3): the Creator IDE Explorer is collapsible. It
 * opens by default where there is more board to find your way around (a Note
 * array of several boards, a FiestaPanel's big grid) and starts closed for a
 * single Flagship or Note, which get the width instead (Figma 53:137378 draws
 * no Explorer; 184:159319 "Full IDE" does).
 */
export function explorerOpenByDefault(kind: DeviceType): boolean {
  return kind === "note_array" || kind === "panel";
}

const storageKey = (kind: DeviceType) => `fiestaboard_ide_explorer:${kind}`;

function readExplorerOpen(kind: DeviceType): boolean {
  try {
    const stored = localStorage.getItem(storageKey(kind));
    if (stored === "open" || stored === "closed") return stored === "open";
  } catch {}
  return explorerOpenByDefault(kind);
}

/**
 * Whether the Explorer is open for pages of this board kind, and a setter
 * that remembers the reader's choice for that kind (not for every page).
 */
export function useExplorerOpen(kind: DeviceType): [boolean, (open: boolean) => void] {
  const [state, setState] = useState(() => ({ kind, open: readExplorerOpen(kind) }));
  // Another page of another kind: that kind's choice, read during render
  // (not in an effect) so the column never flashes the old one.
  if (state.kind !== kind) setState({ kind, open: readExplorerOpen(kind) });
  const setOpen = useCallback(
    (open: boolean) => {
      setState({ kind, open });
      try {
        localStorage.setItem(storageKey(kind), open ? "open" : "closed");
      } catch {}
    },
    [kind],
  );
  return [state.kind === kind ? state.open : readExplorerOpen(kind), setOpen];
}
