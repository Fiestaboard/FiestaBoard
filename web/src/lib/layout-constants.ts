/** Maximum width for the app content area on ultra-wide monitors (in pixels). */
export const MAX_APP_WIDTH = 1920;

/** Base offset for the sidebar from the container edge (matches Tailwind `left-3` / 0.75rem). */
export const SIDEBAR_INSET = 12;

/**
 * Below this width of the desktop editor's header row, the actions beside the
 * page name go icon-only (Update for Save & update board) so the name keeps
 * 240px (BB-E-4). Measured on the row, not the viewport: the nav rail and an
 * open Explorer take room too. Figma draws no frame this narrow (D8).
 */
export const COMPACT_EDITOR_HEADER_WIDTH = 1000;
