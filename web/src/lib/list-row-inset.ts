/**
 * The 07 "inset rows" list: rows that sit inside their card (its 1px border
 * plus 4px), 2px apart, each with its own rounded hover/selected fill and no
 * dividers. Drawn by 07e Settings rows (`320:7936`), 07d Schedule agenda rows
 * (`322:19169`) and 07d Integrations rows (`324:50158`).
 *
 * Composed on the kit's `ListRowGroup` (inset card surface) and `ListRow`
 * from kit spacing tokens, in one place so the three screens cannot drift.
 * The kit's own inset group draws full-bleed rows with dividers; this is the
 * DD-W row recorded for moving it into FiestaUI as a group variant.
 */
export const INSET_ROW_GROUP = "flex flex-col gap-0.5 p-1 divide-y-0";

/** One row in an {@link INSET_ROW_GROUP}: 44px for one line, ~56 for two. */
export const INSET_ROW = "min-h-11 rounded-md py-2";
