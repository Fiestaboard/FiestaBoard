"use client";

import { createContext, useContext } from "react";

/**
 * The template card's header meta (Figma 184:159319 "12 / 12 lines · 29 columns",
 * UX-3-3): page-builder draws the card header and provides this element; the
 * template editor portals its line count and caret readout into it, so the
 * count lives in the header instead of under the card. Null while no header
 * exists (the editor then keeps its own caption).
 */
export const TemplateCardMetaContext = createContext<HTMLElement | null>(null);

export function useTemplateCardMeta(): HTMLElement | null {
  return useContext(TemplateCardMetaContext);
}
