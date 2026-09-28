/** Which formula categories the Insert Formula picker shows, and in what order.
 *
 * Kept out of `FormulaEditorPanel.tsx` so it can be tested without mounting
 * CodeMirror.
 *
 * The picker used to iterate `CATEGORY_ORDER` alone, which silently hid every
 * function in a category the API had added — that is how the `array` and
 * `date` families could ship server-side and still be missing from the picker.
 * `categoriesToRender` appends unknown categories instead of dropping them.
 */

/** Known categories, in the order the picker lists them. */
export const CATEGORY_ORDER = ["logic", "array", "date", "math", "text", "convert", "color"] as const;

/** Known categories first (in order), then any others the API returned. */
export function categoriesToRender(grouped: Record<string, unknown[] | undefined>): string[] {
  const known = CATEGORY_ORDER.filter((cat) => grouped[cat]?.length);
  const unknown = Object.keys(grouped)
    .filter((cat) => !(CATEGORY_ORDER as readonly string[]).includes(cat) && grouped[cat]?.length)
    .sort();
  return [...known, ...unknown];
}
