/** Search authored content only: no rendering, provider requests or cache writes. */
export const PAGE_LIBRARY_SORTS = [
  "name-asc",
  "name-desc",
  "created-desc",
  "created-asc",
  "updated-desc",
  "updated-asc",
] as const;
export type PageLibrarySort = (typeof PAGE_LIBRARY_SORTS)[number];
export interface PageLibraryQuery {
  text: string;
  sort: PageLibrarySort;
}

/** Structural input also accepts flexible documents without importing their editor. */
interface LibraryPage {
  id: string;
  name: string;
  created_at?: string | null;
  updated_at?: string | null;
  template?: unknown;
  display_type?: unknown;
  rows?: unknown;
  canvases?: unknown;
  blocks?: unknown;
  style?: unknown;
}

function record(value: unknown): Record<string, unknown> | undefined {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;
}
function list(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}
function normalized(value: string): string {
  return value.normalize("NFC").toLowerCase();
}

const EXPRESSION_FIELDS = [
  "if",
  "foreach",
  "x",
  "y",
  "w",
  "h",
  "width",
  "height",
  "x1",
  "y1",
  "x2",
  "y2",
  "cx",
  "cy",
  "r",
  "rx",
  "ry",
  "points",
  "color",
  "background",
  "fill",
  "stroke",
  "opacity",
  "from",
  "to",
  "angle",
];
const SHAPE_TYPES = new Set(["rect", "line", "circle", "ellipse", "polygon", "text", "gradient"]);

export function pageLibrarySearchText(page: LibraryPage): string {
  const parts = [page.name];
  const add = (value: unknown) => {
    if (typeof value === "string") parts.push(value);
  };
  const expression = (value: unknown) => {
    if (typeof value === "string" && value.includes("{{") && value.includes("}}")) add(value);
  };
  const expressions = (value: unknown) => {
    const fields = record(value);
    for (const key of EXPRESSION_FIELDS) {
      expression(fields?.[key]);
    }
  };
  const canvas = (value: unknown) => {
    const item = record(value);
    add(item?.source);
    const content = record(item?.content);
    expressions(content);
    for (const value of list(content?.shapes)) {
      const shape = record(value);
      if (!shape || !SHAPE_TYPES.has(String(shape.type))) continue;
      if (shape.type === "text") add(shape.text);
      expressions(shape);
      if (shape.type === "polygon") {
        for (const point of list(shape.points)) {
          for (const coordinate of list(point)) expression(coordinate);
        }
      }
    }
  };
  for (const line of list(page.template)) add(line);
  add(page.display_type);
  for (const row of list(page.rows)) add(record(row)?.source);
  for (const value of list(page.canvases)) canvas(value);
  expressions(page.style);
  for (const value of list(page.blocks)) {
    const block = record(value);
    if (!block || !["text", "canvas", "spacer"].includes(String(block.kind))) continue;
    expressions(block);
    expressions(block.style);
    if (block.kind === "text") add(block.text);
    if (block.kind === "canvas") canvas(block.canvas);
  }
  return normalized(parts.join(" "));
}

function compareText(a: string, b: string): number {
  return a < b ? -1 : a > b ? 1 : 0;
}
function timestamp(value: string | null | undefined): number | null {
  const parsed = typeof value === "string" ? Date.parse(value) : NaN;
  return Number.isFinite(parsed) ? parsed : null;
}

export function selectLibraryPages<T extends LibraryPage>(
  pages: readonly T[],
  query: PageLibraryQuery,
  locale = "en",
): T[] {
  const words = normalized(query.text).trim().split(/\s+/).filter(Boolean);
  const filtered = pages.filter((page) => {
    if (!words.length) return true;
    const content = pageLibrarySearchText(page);
    return words.every((word) => content.includes(word));
  });
  const names = new Intl.Collator(locale, { sensitivity: "accent" });
  return filtered.sort((a, b) => {
    const nameOrder = names.compare(a.name, b.name);
    if (query.sort.startsWith("name-")) {
      return nameOrder * (query.sort === "name-desc" ? -1 : 1) || compareText(a.id, b.id);
    }
    const updated = query.sort.startsWith("updated-");
    const aTime = timestamp(updated ? (a.updated_at ?? a.created_at) : a.created_at);
    const bTime = timestamp(updated ? (b.updated_at ?? b.created_at) : b.created_at);
    if (aTime === null && bTime !== null) return 1;
    if (aTime !== null && bTime === null) return -1;
    const dateOrder = aTime === null || bTime === null ? 0 : aTime - bTime;
    return dateOrder * (query.sort.endsWith("desc") ? -1 : 1) || nameOrder || compareText(a.id, b.id);
  });
}
