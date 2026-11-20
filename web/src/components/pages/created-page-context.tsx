"use client";

import { createContext, useContext } from "react";

/**
 * Tells the Pages section that /pages/new just created its page (BB-B-9).
 * The editor stays mounted and only the address changes, so the router still
 * reports /pages/new; the section reads the page's id from here instead.
 */
export const CreatedPageContext = createContext<((pageId: string) => void) | null>(null);

export function useReportCreatedPage(): ((pageId: string) => void) | null {
  return useContext(CreatedPageContext);
}
