// How wide the FiestaBot drawer is, and where that number lives.
//
// The drawer used to be 384px for everyone, with the page reserving a
// hardcoded 396px beside it. A transcript full of tool cards and board
// previews wants more room on a large screen and none of it on a laptop, so
// the width is the viewer's to choose: dragged or nudged with the keyboard,
// kept in localStorage, and published as a CSS custom property that the
// page's own reservation follows (globals.css).
//
// The clamps are not decoration. Below ~360px the composer toolbar has no
// room for its controls; above 40% of the viewport the drawer stops being a
// drawer and the page behind it stops being readable.

/** What the drawer opens at before anyone touches it. */
export const DEFAULT_AI_DRAWER_WIDTH = 384;

/** Narrowest useful drawer: the composer's controls still fit on one row. */
export const MIN_AI_DRAWER_WIDTH = 360;

/** Widest drawer on any screen, before the viewport cap applies. */
export const MAX_AI_DRAWER_WIDTH = 720;

/** The drawer may not take more of the window than this. */
const MAX_VIEWPORT_FRACTION = 0.4;

export const AI_DRAWER_WIDTH_STORAGE_KEY = "fiestaboard:ai-drawer-width";

/** The custom property the drawer publishes and `globals.css` reserves by. */
export const AI_DRAWER_WIDTH_VAR = "--ai-drawer-width";

/** The class that tells the page a drawer is open and reserving width. */
export const AI_DRAWER_OPEN_CLASS = "ai-drawer-open";

/** The class that suppresses the width transition while a drag is live. */
export const AI_DRAWER_DRAGGING_CLASS = "ai-drawer-dragging";

/**
 * The widest the drawer may be on this viewport: 40% of it, the 720px
 * ceiling, and never narrower than the floor (a phone-sized window would
 * otherwise compute a maximum below the minimum).
 */
export function maxDrawerWidth(viewportWidth: number): number {
  if (!Number.isFinite(viewportWidth) || viewportWidth <= 0) return MAX_AI_DRAWER_WIDTH;
  return Math.max(
    MIN_AI_DRAWER_WIDTH,
    Math.min(MAX_AI_DRAWER_WIDTH, Math.round(viewportWidth * MAX_VIEWPORT_FRACTION)),
  );
}

/** A requested width, brought inside the range this viewport allows. */
export function clampDrawerWidth(width: number, viewportWidth: number): number {
  if (!Number.isFinite(width)) return DEFAULT_AI_DRAWER_WIDTH;
  return Math.min(Math.max(Math.round(width), MIN_AI_DRAWER_WIDTH), maxDrawerWidth(viewportWidth));
}

/**
 * The width this viewer last chose, or null.
 *
 * Null covers every way there is no usable answer — nothing stored, junk
 * stored, storage unavailable (private mode, blocked site data) — so the
 * caller has exactly one fallback path to the default.
 */
export function readStoredDrawerWidth(): number | null {
  try {
    const raw = localStorage.getItem(AI_DRAWER_WIDTH_STORAGE_KEY);
    if (raw === null) return null;
    const parsed = Number.parseInt(raw, 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  } catch {
    return null;
  }
}

/** Remember the width. A storage failure is never worth breaking a drag over. */
export function storeDrawerWidth(width: number): void {
  try {
    localStorage.setItem(AI_DRAWER_WIDTH_STORAGE_KEY, String(Math.round(width)));
  } catch {
    /* storage may be unavailable; the width simply does not persist */
  }
}
