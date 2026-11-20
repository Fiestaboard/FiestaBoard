/** Maximum width for the app content area on ultra-wide monitors (in pixels). */
export const MAX_APP_WIDTH = 1920;

/** Base offset for the sidebar from the container edge (matches Tailwind `left-3` / 0.75rem). */
export const SIDEBAR_INSET = 12;

/**
 * The desktop editor between the `lg` rail and 1280px: the header actions
 * beside the page name go icon-only (or short) so the name keeps 240px
 * (BB-E-4). Figma draws no frame here (D8).
 */
export const COMPACT_EDITOR_HEADER_QUERY = "(min-width: 1024px) and (max-width: 1279.98px)";
