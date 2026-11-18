// Builder recipes (04c C2): each form writes plain formula text with real
// built-ins only, so Builder → Code is always lossless.

export type RecipeId = "either" | "fallback" | "threshold" | "list" | "countdown" | "date";

export const RECIPE_IDS: readonly RecipeId[] = ["either", "fallback", "threshold", "list", "countdown", "date"];

export interface ListColumn {
  /** Item field, read as `item.<field>`. */
  field: string;
  label: string;
  /** FORMATDATE pattern for a date/time field. */
  format?: string;
  upper: boolean;
  /** Tiles the column takes on the board. */
  width: number;
  /** `pad` fills to the width, `left` cuts at it, `none` leaves the value as is (ignored with `format`). */
  cut: "pad" | "left" | "none";
}

export type RecipeForm =
  | { recipe: "either"; condition: string; then: string; otherwise: string }
  | { recipe: "fallback"; value: string; fallback: string }
  | { recipe: "threshold"; value: string; threshold: number; above: string; below: string }
  | { recipe: "list"; list: string; take: number; columns: ListColumn[]; empty: string }
  | { recipe: "countdown"; value: string; unit: "minutes" | "hours" | "days"; suffix: string }
  | { recipe: "date"; value: string; pattern: string };

/** A text literal. The formula language has no quote escape, so quotes are dropped. */
export function literal(text: string): string {
  return `"${text.replaceAll('"', "")}"`;
}

/** The expression for one list column. */
export function listColumnExpr(column: ListColumn): string {
  let expr = `item.${column.field}`;
  if (column.format) expr = `FORMATDATE(DATE(${expr}), ${literal(column.format)})`;
  if (column.upper) expr = `UPPER(${expr})`;
  // A date pattern already fixes the width.
  if (column.format) return expr;
  if (column.cut === "pad") expr = `PAD(${expr}, ${column.width})`;
  if (column.cut === "left") expr = `LEFT(${expr}, ${column.width})`;
  return expr;
}

/** Every column plus one space between columns, against the board width. */
export function columnBudget(
  columns: readonly ListColumn[],
  boardCols: number,
): { widths: number[]; spaces: number; total: number; fits: boolean } {
  const widths = columns.map((column) => column.width);
  const spaces = Math.max(columns.length - 1, 0);
  const total = widths.reduce((sum, width) => sum + width, 0) + spaces;
  return { widths, spaces, total, fits: total <= boardCols };
}

const blank = (text: string) => text.trim().length === 0;

/** The formula a recipe form writes, or "" while the form is incomplete. */
export function buildRecipe(form: RecipeForm): string {
  switch (form.recipe) {
    case "either":
      if (blank(form.condition)) return "";
      return `IF(${form.condition.trim()}, ${literal(form.then)}, ${literal(form.otherwise)})`;
    case "fallback":
      if (blank(form.value)) return "";
      return `DEFAULT(${form.value.trim()}, ${literal(form.fallback)})`;
    case "threshold":
      if (blank(form.value) || !Number.isFinite(form.threshold)) return "";
      return `IF(${form.value.trim()} > ${form.threshold}, COLOR(${literal(form.above)}), COLOR(${literal(form.below)}))`;
    case "list": {
      if (blank(form.list) || form.columns.length === 0) return "";
      const row = form.columns.map(listColumnExpr).join(' & " " & ');
      const list = form.list.trim();
      const rows = `FOREACH(SLICE(${list}, 0, ${form.take}), ${row})`;
      return blank(form.empty) ? rows : `IF(COUNT(${list}) = 0, ${literal(form.empty)}, ${rows})`;
    }
    case "countdown": {
      if (blank(form.value)) return "";
      const diff = `DATEDIFF(NOW(), DATE(${form.value.trim()}), ${literal(form.unit)})`;
      return blank(form.suffix) ? diff : `${diff} & ${literal(` ${form.suffix.trim()}`)}`;
    }
    case "date":
      if (blank(form.pattern)) return "";
      return `FORMATDATE(${blank(form.value) ? "NOW()" : `DATE(${form.value.trim()})`}, ${literal(form.pattern)})`;
  }
}
