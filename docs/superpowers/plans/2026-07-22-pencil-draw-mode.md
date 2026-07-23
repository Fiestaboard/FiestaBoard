# Pencil Draw Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A pencil toggle in the rich template editor toolbar that lets users paint board tiles with a selected color (or eraser) by clicking/dragging on the board preview, with full undo/redo, across all device types.

**Architecture:** The template string stays the single source of truth. Painting cell (row, col) rewrites template line `row` so cell `col` is a `{{color}}` marker (or blank). Paints are applied to the TipTap document as single ProseMirror transactions (one per stroke, `closeHistory` boundary between strokes) so ProseMirror history provides undo/redo. The preview becomes a paint surface via a delegated-pointer-listener wrapper (`DrawableBoardPreview`) that hit-tests tiles by new `data-row`/`data-col` attributes — no per-cell handlers, no coordinate math (immune to `ScaledBoardDisplay`'s CSS scale). In draw mode the preview renders through the static tile path and composes painted (positional) lines client-side for instant feedback.

**Tech Stack:** React 19, TipTap 3 / ProseMirror, TanStack Query, Vitest (unit, `web/src/__tests__/`), Playwright (e2e, `web/tests/`), react-i18next (14 locales in `web/messages/`).

**Spec:** `docs/superpowers/specs/2026-07-22-pencil-draw-mode-design.md`

## Global Constraints

- NEVER run API/UI/npm/pip directly on the host. All test/build commands run in Docker: `docker compose -f docker-compose.dev.yml ...` (CLAUDE.md).
- Web unit tests: `docker compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npx vitest run <path>"`.
- CI lint-web runs `prettier --check` — run `npx prettier --write` on touched web files before every commit (inside the web test container: `sh -c "npm ci && npx prettier --write <files>"`; running prettier via the container is the compliant path).
- UI changes are NOT hot-reloaded in the dev container; e2e runs require a container rebuild first (`docker compose -f docker-compose.dev.yml build` then `up -d`).
- New user-facing strings go in `web/messages/en.json` AND all other 13 locale files (de, es, fr, it, ja, ko, nl, pl, pt, ru, sv, tr, zh) with translated values.
- No temporary markdown files in repo root. Frequent commits with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Branch: `feat-pencil-draw-mode` (already created).
- Work in `web/` unless stated. TDD: write the failing test first for every unit of logic.

---

### Task 1: Draw-mode utilities (pure functions)

**Files:**
- Create: `web/src/components/tiptap-template-editor/utils/draw-mode.ts`
- Test: `web/src/__tests__/draw-mode-utils.test.ts`

**Interfaces:**
- Consumes: `BOARD_COLORS`, `BoardColorName` from `web/src/components/tiptap-template-editor/utils/constants.ts`.
- Produces (used by Tasks 5, 6, 7):
  - `type DrawBrush = BoardColorName | "eraser"`
  - `type Cell = string` (single char, or `"{{red}}"`-style color marker)
  - `lineToCells(line: string): Cell[]`
  - `cellsToLine(cells: Cell[]): string`
  - `isPositionalLine(line: string): boolean`
  - `renderPositionalLine(line: string): string`
  - `interface CellPaint { col: number; color: BoardColorName | null }` (null = erase)
  - `paintLine(line: string, paints: CellPaint[], cols: number): string`

- [ ] **Step 1: Write the failing tests** — `web/src/__tests__/draw-mode-utils.test.ts`:

```ts
import { describe, expect, it } from "vitest";

import {
  cellsToLine,
  isPositionalLine,
  lineToCells,
  paintLine,
  renderPositionalLine,
} from "@/components/tiptap-template-editor/utils/draw-mode";

describe("lineToCells", () => {
  it("splits literal characters into one cell each", () => {
    expect(lineToCells("AB C")).toEqual(["A", "B", " ", "C"]);
  });
  it("treats {{color}} as a single cell", () => {
    expect(lineToCells("A{{red}}B")).toEqual(["A", "{{red}}", "B"]);
  });
  it("normalizes single-bracket named colors to double-bracket cells", () => {
    expect(lineToCells("{red}X")).toEqual(["{{red}}", "X"]);
  });
  it("normalizes numeric color codes 63-70 to named cells", () => {
    expect(lineToCells("{63}{67}")).toEqual(["{{red}}", "{{blue}}"]);
  });
  it("maps filled-tile code 71 to black", () => {
    expect(lineToCells("{71}")).toEqual(["{{black}}"]);
  });
  it("drops dynamic tokens (variables, fill_space, formulas, wrap)", () => {
    expect(lineToCells("A{{weather.temp}}B")).toEqual(["A", "B"]);
    expect(lineToCells("{{fill_space}}X")).toEqual(["X"]);
    expect(lineToCells("{{= 1 + 2 }}X")).toEqual(["X"]);
    expect(lineToCells("{{long text|wrap}}X")).toEqual(["X"]);
  });
  it("keeps non-color single-bracket tokens as literal characters", () => {
    expect(lineToCells("{sun}")).toEqual(["{", "s", "u", "n", "}"]);
  });
});

describe("cellsToLine", () => {
  it("joins cells and trims trailing blanks", () => {
    expect(cellsToLine(["A", " ", "{{red}}", " ", " "])).toBe("A {{red}}");
  });
  it("returns empty string for all-blank cells", () => {
    expect(cellsToLine([" ", " "])).toBe("");
  });
});

describe("isPositionalLine", () => {
  it("is true for literals and colors", () => {
    expect(isPositionalLine("AB {{red}} {blue}")).toBe(true);
    expect(isPositionalLine("")).toBe(true);
  });
  it("is false when a dynamic token is present", () => {
    expect(isPositionalLine("A{{weather.temp}}")).toBe(false);
    expect(isPositionalLine("{{fill_space}}")).toBe(false);
    expect(isPositionalLine("{{= 1 }}")).toBe(false);
  });
});

describe("paintLine", () => {
  it("paints a color into an empty line, padding with blanks", () => {
    expect(paintLine("", [{ col: 3, color: "red" }], 22)).toBe("   {{red}}");
  });
  it("overwrites an existing character", () => {
    expect(paintLine("HELLO", [{ col: 1, color: "blue" }], 22)).toBe("H{{blue}}LLO");
  });
  it("erases with null color", () => {
    expect(paintLine("HELLO", [{ col: 4, color: null }], 22)).toBe("HELL");
  });
  it("applies multiple paints in one call", () => {
    expect(
      paintLine("", [
        { col: 0, color: "red" },
        { col: 2, color: "red" },
      ], 22),
    ).toBe("{{red}} {{red}}");
  });
  it("strips dynamic tokens when painting a line containing them", () => {
    expect(paintLine("HI {{weather.temp}}", [{ col: 0, color: "green" }], 22)).toBe("{{green}}I");
  });
  it("ignores out-of-bounds columns", () => {
    expect(paintLine("AB", [{ col: 30, color: "red" }, { col: -1, color: "red" }], 22)).toBe("AB");
  });
  it("truncates content beyond the board width", () => {
    const long = "X".repeat(30);
    expect(paintLine(long, [{ col: 0, color: "red" }], 22)).toBe("{{red}}" + "X".repeat(21));
  });
});

describe("renderPositionalLine", () => {
  it("converts color cells to single-bracket render form", () => {
    expect(renderPositionalLine("A{{red}}B")).toBe("A{red}B");
  });
  it("passes literals through and drops dynamic tokens", () => {
    expect(renderPositionalLine("HI {{weather.temp}}!")).toBe("HI !");
  });
});
```

- [ ] **Step 2: Run tests, verify they fail** (module not found):
`docker compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npx vitest run src/__tests__/draw-mode-utils.test.ts"` → FAIL.

- [ ] **Step 3: Implement** `web/src/components/tiptap-template-editor/utils/draw-mode.ts`:

```ts
/**
 * Draw-mode utilities — cell-level editing of template lines.
 *
 * A "positional" line maps 1:1 to board cells: each literal character is one
 * cell and each color marker ({{red}}) is one cell. Dynamic tokens
 * (variables, fill_space, formulas, wrapped text) have no fixed width, so
 * painting a line drops them (the user is choosing to draw over them; undo
 * restores).
 */

import { BOARD_COLORS, type BoardColorName } from "./constants";

export type DrawBrush = BoardColorName | "eraser";

/** One board cell: a single literal character, or a "{{color}}" marker. */
export type Cell = string;

export interface CellPaint {
  col: number;
  /** Color to paint, or null to erase (blank the cell). */
  color: BoardColorName | null;
}

const COLOR_CELL_RE = /^\{\{([a-z]+)\}\}$/;

/** Numeric board codes → color names (71 = filled tile, closest is black). */
const CODE_TO_NAME: Record<number, BoardColorName> = {
  63: "red",
  64: "orange",
  65: "yellow",
  66: "green",
  67: "blue",
  68: "violet",
  69: "white",
  70: "black",
  71: "black",
};

function colorCell(color: BoardColorName): Cell {
  return `{{${color}}}`;
}

export function lineToCells(line: string): Cell[] {
  const cells: Cell[] = [];
  let remaining = line;

  while (remaining.length > 0) {
    const dbl = remaining.match(/^\{\{([^}]+)\}\}/);
    if (dbl) {
      const content = dbl[1].trim().toLowerCase();
      if (content in BOARD_COLORS) {
        cells.push(colorCell(content as BoardColorName));
      }
      // Non-color {{...}} tokens are dynamic — dropped.
      remaining = remaining.slice(dbl[0].length);
      continue;
    }

    const single = remaining.match(/^\{([a-z0-9]+)\}/i);
    if (single) {
      const token = single[1].toLowerCase();
      const numeric = Number(token);
      if (token in BOARD_COLORS) {
        cells.push(colorCell(token as BoardColorName));
        remaining = remaining.slice(single[0].length);
        continue;
      }
      if (Number.isInteger(numeric) && numeric >= 63 && numeric <= 71) {
        cells.push(colorCell(CODE_TO_NAME[numeric]));
        remaining = remaining.slice(single[0].length);
        continue;
      }
      // Not a color token — fall through to literal handling below.
    }

    cells.push(remaining[0]);
    remaining = remaining.slice(1);
  }

  return cells;
}

export function cellsToLine(cells: Cell[]): string {
  let end = cells.length;
  while (end > 0 && cells[end - 1] === " ") end--;
  return cells.slice(0, end).join("");
}

export function isPositionalLine(line: string): boolean {
  const re = /\{\{([^}]+)\}\}/g;
  let match: RegExpExecArray | null;
  while ((match = re.exec(line))) {
    if (!(match[1].trim().toLowerCase() in BOARD_COLORS)) return false;
  }
  return true;
}

export function paintLine(line: string, paints: CellPaint[], cols: number): string {
  const cells = lineToCells(line);
  if (cells.length > cols) cells.length = cols;

  const validPaints = paints.filter((p) => p.col >= 0 && p.col < cols);
  for (const paint of validPaints) {
    while (cells.length <= paint.col) cells.push(" ");
    cells[paint.col] = paint.color ? colorCell(paint.color) : " ";
  }
  return cellsToLine(cells);
}

/**
 * Render a positional line for BoardDisplay's parser, which expects
 * single-bracket color markers ({red}) after server-side rendering.
 */
export function renderPositionalLine(line: string): string {
  return lineToCells(line)
    .map((cell) => {
      const m = cell.match(COLOR_CELL_RE);
      return m ? `{${m[1]}}` : cell;
    })
    .join("");
}
```

- [ ] **Step 4: Run tests, verify PASS** (same command as Step 2).
- [ ] **Step 5: Prettier + commit**: `git add web/src/components/tiptap-template-editor/utils/draw-mode.ts web/src/__tests__/draw-mode-utils.test.ts && git commit -m "feat(draw-mode): add cell-level template line utilities"`.

---

### Task 2: Tile coordinates on BoardDisplay

**Files:**
- Modify: `web/src/components/board-display.tsx` (StaticGridRow ~line 300-343, GridRow ~line 350-427)
- Test: `web/src/__tests__/board-display-draw-attrs.test.tsx`

**Interfaces:**
- Produces: every tile wrapper div (`[data-note-tile]`) in BOTH render paths gains `data-row={rowIdx}` and `data-col={colIdx}`. Static-path wrappers additionally gain `data-cell-value` = the token's char/color-code (via existing `getCharFromToken`). Used by Tasks 3, 7, 8 for hit-testing and assertions.

- [ ] **Step 1: Failing test** — `web/src/__tests__/board-display-draw-attrs.test.tsx`:

```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { BoardDisplay } from "@/components/board-display";

describe("BoardDisplay tile coordinates", () => {
  it("exposes data-row/data-col on static tiles with cell values", () => {
    const { container } = render(<BoardDisplay message={"A{red}"} isStatic />);
    const a = container.querySelector('[data-row="0"][data-col="0"]');
    const red = container.querySelector('[data-row="0"][data-col="1"]');
    expect(a).not.toBeNull();
    expect(a!.getAttribute("data-cell-value")).toBe("A");
    expect(red!.getAttribute("data-cell-value")).toBe("red");
    // full flagship grid present
    expect(container.querySelector('[data-row="5"][data-col="21"]')).not.toBeNull();
  });

  it("exposes data-row/data-col on animated tiles", () => {
    const { container } = render(<BoardDisplay message={"HI"} />);
    expect(container.querySelector('[data-row="0"][data-col="1"]')).not.toBeNull();
  });
});
```

- [ ] **Step 2: Run to verify FAIL**: `... npx vitest run src/__tests__/board-display-draw-attrs.test.tsx`.
- [ ] **Step 3: Implement.** In `StaticGridRow`'s tile wrapper div (currently `data-note-tile=""` around line 331), add:

```tsx
data-row={rowIdx}
data-col={colIdx}
data-cell-value={getCharFromToken(token)}
```

In `GridRow`'s tile wrapper div (around line 387), add `data-row={rowIdx}` and `data-col={colIdx}` (no `data-cell-value` — the animated path already exposes `data-target-char` inside `CharTile`).

- [ ] **Step 4: Run test → PASS.** Also run the existing board display test to catch regressions: `npx vitest run src/__tests__/board-display-variable-size.test.tsx src/__tests__/board-display-draw-attrs.test.tsx`.
- [ ] **Step 5: Prettier + commit** `feat(draw-mode): expose tile coordinates on board display`.

---

### Task 3: DrawableBoardPreview pointer-capture wrapper

**Files:**
- Create: `web/src/components/drawable-board-preview.tsx`
- Test: `web/src/__tests__/drawable-board-preview.test.tsx`

**Interfaces:**
- Produces (used by Task 7):

```ts
export interface StrokeCell { row: number; col: number }
interface DrawableBoardPreviewProps {
  active: boolean;
  /** rAF-throttled set of unique cells hit so far in the in-progress stroke. */
  onStrokePreview: (cells: StrokeCell[]) => void;
  /** Fired once on pointerup with the full stroke; preview should be cleared by the parent. */
  onStrokeCommit: (cells: StrokeCell[]) => void;
  children: React.ReactNode;
}
export function DrawableBoardPreview(props: DrawableBoardPreviewProps): JSX.Element
```

- [ ] **Step 1: Failing tests** — `web/src/__tests__/drawable-board-preview.test.tsx`. jsdom has no layout, so stub `document.elementFromPoint` to return tiles by coordinates:

```tsx
import { fireEvent, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DrawableBoardPreview } from "@/components/drawable-board-preview";

function makeTile(row: number, col: number): HTMLElement {
  const el = document.createElement("div");
  el.setAttribute("data-row", String(row));
  el.setAttribute("data-col", String(col));
  document.body.appendChild(el);
  return el;
}

describe("DrawableBoardPreview", () => {
  beforeEach(() => {
    vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
      cb(0);
      return 1;
    });
    vi.stubGlobal("cancelAnimationFrame", () => {});
    // jsdom lacks pointer capture
    Element.prototype.setPointerCapture = Element.prototype.setPointerCapture || (() => {});
    Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture || (() => {});
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  function setup(active = true) {
    const onStrokePreview = vi.fn();
    const onStrokeCommit = vi.fn();
    const utils = render(
      <DrawableBoardPreview active={active} onStrokePreview={onStrokePreview} onStrokeCommit={onStrokeCommit}>
        <div data-testid="board" />
      </DrawableBoardPreview>,
    );
    const surface = utils.getByTestId("board").parentElement as HTMLElement;
    return { surface, onStrokePreview, onStrokeCommit };
  }

  it("commits a single-cell stroke on click", () => {
    const { surface, onStrokePreview, onStrokeCommit } = setup();
    const tile = makeTile(1, 3);
    document.elementFromPoint = vi.fn().mockReturnValue(tile);

    fireEvent.pointerDown(surface, { button: 0, clientX: 5, clientY: 5, pointerId: 1 });
    expect(onStrokePreview).toHaveBeenCalledWith([{ row: 1, col: 3 }]);
    fireEvent.pointerUp(surface, { pointerId: 1 });
    expect(onStrokeCommit).toHaveBeenCalledWith([{ row: 1, col: 3 }]);
  });

  it("accumulates unique cells across a drag", () => {
    const { surface, onStrokeCommit } = setup();
    const t1 = makeTile(0, 0);
    const t2 = makeTile(0, 1);
    const efp = vi.fn().mockReturnValueOnce(t1).mockReturnValueOnce(t2).mockReturnValue(t2);
    document.elementFromPoint = efp;

    fireEvent.pointerDown(surface, { button: 0, pointerId: 1 });
    fireEvent.pointerMove(surface, { pointerId: 1 });
    fireEvent.pointerMove(surface, { pointerId: 1 }); // same tile again — deduped
    fireEvent.pointerUp(surface, { pointerId: 1 });

    expect(onStrokeCommit).toHaveBeenCalledWith([
      { row: 0, col: 0 },
      { row: 0, col: 1 },
    ]);
    expect(onStrokeCommit).toHaveBeenCalledTimes(1);
  });

  it("does nothing when inactive", () => {
    const { surface, onStrokePreview, onStrokeCommit } = setup(false);
    document.elementFromPoint = vi.fn().mockReturnValue(makeTile(0, 0));
    fireEvent.pointerDown(surface, { button: 0, pointerId: 1 });
    fireEvent.pointerUp(surface, { pointerId: 1 });
    expect(onStrokePreview).not.toHaveBeenCalled();
    expect(onStrokeCommit).not.toHaveBeenCalled();
  });

  it("clears the stroke without committing on pointercancel", () => {
    const { surface, onStrokePreview, onStrokeCommit } = setup();
    document.elementFromPoint = vi.fn().mockReturnValue(makeTile(0, 0));
    fireEvent.pointerDown(surface, { button: 0, pointerId: 1 });
    fireEvent.pointerCancel(surface, { pointerId: 1 });
    expect(onStrokeCommit).not.toHaveBeenCalled();
    expect(onStrokePreview).toHaveBeenLastCalledWith([]);
  });
});
```

- [ ] **Step 2: Run → FAIL** (module not found).
- [ ] **Step 3: Implement** `web/src/components/drawable-board-preview.tsx`:

```tsx
"use client";

/**
 * Wraps the board preview with a single delegated pointer listener that
 * turns clicks/drags over tiles into paint strokes. Hit-testing uses the
 * tiles' data-row/data-col attributes via elementFromPoint, so
 * ScaledBoardDisplay's CSS transform never enters coordinate math.
 */

import { useCallback, useEffect, useRef } from "react";
import type { ReactNode } from "react";

export interface StrokeCell {
  row: number;
  col: number;
}

interface DrawableBoardPreviewProps {
  active: boolean;
  onStrokePreview: (cells: StrokeCell[]) => void;
  onStrokeCommit: (cells: StrokeCell[]) => void;
  children: ReactNode;
}

function cellAtPoint(x: number, y: number): StrokeCell | null {
  const el = document.elementFromPoint(x, y);
  const tile = el?.closest?.("[data-row][data-col]") as HTMLElement | null;
  if (!tile) return null;
  const row = Number(tile.dataset.row);
  const col = Number(tile.dataset.col);
  if (!Number.isInteger(row) || !Number.isInteger(col)) return null;
  return { row, col };
}

export function DrawableBoardPreview({ active, onStrokePreview, onStrokeCommit, children }: DrawableBoardPreviewProps) {
  const strokeRef = useRef<Map<string, StrokeCell> | null>(null);
  const rafRef = useRef<number | null>(null);

  const flushPreview = useCallback(() => {
    rafRef.current = null;
    if (strokeRef.current) onStrokePreview([...strokeRef.current.values()]);
  }, [onStrokePreview]);

  const schedulePreview = useCallback(() => {
    if (rafRef.current === null) rafRef.current = requestAnimationFrame(flushPreview);
  }, [flushPreview]);

  const abortStroke = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (strokeRef.current) {
      strokeRef.current = null;
      onStrokePreview([]);
    }
  }, [onStrokePreview]);

  // Leaving draw mode mid-stroke must not leave a dangling stroke.
  useEffect(() => {
    if (!active) abortStroke();
  }, [active, abortStroke]);

  const handlePointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!active || e.button !== 0) return;
    const cell = cellAtPoint(e.clientX, e.clientY);
    if (!cell) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    strokeRef.current = new Map([[`${cell.row}:${cell.col}`, cell]]);
    schedulePreview();
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!strokeRef.current) return;
    const cell = cellAtPoint(e.clientX, e.clientY);
    if (!cell) return;
    const key = `${cell.row}:${cell.col}`;
    if (!strokeRef.current.has(key)) {
      strokeRef.current.set(key, cell);
      schedulePreview();
    }
  };

  const handlePointerUp = () => {
    if (!strokeRef.current) return;
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    const cells = [...strokeRef.current.values()];
    strokeRef.current = null;
    onStrokeCommit(cells);
  };

  return (
    <div
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onPointerCancel={abortStroke}
      className={active ? "cursor-crosshair select-none" : undefined}
      style={active ? { touchAction: "none" } : undefined}
      data-draw-surface={active ? "true" : undefined}
    >
      {children}
    </div>
  );
}
```

- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Prettier + commit** `feat(draw-mode): add DrawableBoardPreview stroke capture`.

---

### Task 4: Draw color picker + i18n strings

**Files:**
- Create: `web/src/components/tiptap-template-editor/components/DrawColorPickerContent.tsx`
- Modify: `web/messages/en.json` (+ the 13 other locale files) — `templateEditor` namespace
- Modify: `web/src/components/tiptap-template-editor/components/ToolbarDropdown.tsx` — add optional `disabled` and `data-testid` props on the trigger button (read the file first; it has a single trigger `<button>`)
- Test: `web/src/__tests__/draw-color-picker.test.tsx`

**Interfaces:**
- Consumes: `AVAILABLE_COLORS`, `getBoardColor` from `web/src/lib/board-colors.ts`; `DrawBrush` from Task 1.
- Produces (used by Task 5):

```ts
interface DrawColorPickerContentProps {
  current: DrawBrush;
  onSelect: (brush: DrawBrush) => void;
}
export function DrawColorPickerContent(props: DrawColorPickerContentProps): JSX.Element
```

Each swatch button: `data-testid="draw-color-<name>"`, eraser: `data-testid="draw-color-eraser"`, current selection gets a visible ring + `aria-pressed`.

- [ ] **Step 1: Failing test** — `web/src/__tests__/draw-color-picker.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DrawColorPickerContent } from "@/components/tiptap-template-editor/components/DrawColorPickerContent";

describe("DrawColorPickerContent", () => {
  it("renders 8 colors plus eraser and reports selection", () => {
    const onSelect = vi.fn();
    render(<DrawColorPickerContent current="red" onSelect={onSelect} />);

    for (const name of ["red", "orange", "yellow", "green", "blue", "violet", "white", "black"]) {
      expect(screen.getByTestId(`draw-color-${name}`)).toBeInTheDocument();
    }
    expect(screen.getByTestId("draw-color-red")).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByTestId("draw-color-blue"));
    expect(onSelect).toHaveBeenCalledWith("blue");

    fireEvent.click(screen.getByTestId("draw-color-eraser"));
    expect(onSelect).toHaveBeenCalledWith("eraser");
  });
});
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement the component.** Model layout on `ColorPickerContent.tsx` (read it for classnames). Sketch:

```tsx
"use client";

import { Eraser } from "lucide-react";

import { useTranslations } from "@/i18n/translations";
import { AVAILABLE_COLORS, getBoardColor } from "@/lib/board-colors";
import { cn } from "@/lib/utils";

import type { DrawBrush } from "../utils/draw-mode";

interface DrawColorPickerContentProps {
  current: DrawBrush;
  onSelect: (brush: DrawBrush) => void;
}

export function DrawColorPickerContent({ current, onSelect }: DrawColorPickerContentProps) {
  const t = useTranslations("templateEditor");
  return (
    <div className="p-2 w-48">
      <div className="grid grid-cols-4 gap-2">
        {AVAILABLE_COLORS.map((name) => (
          <button
            key={name}
            type="button"
            data-testid={`draw-color-${name}`}
            aria-pressed={current === name}
            aria-label={t(`drawColors.${name}`)}
            onClick={() => onSelect(name as DrawBrush)}
            className={cn(
              "h-8 w-8 rounded-md border transition-shadow",
              current === name ? "ring-2 ring-primary ring-offset-1" : "hover:ring-1 hover:ring-muted-foreground",
            )}
            style={{ backgroundColor: getBoardColor(name) }}
          />
        ))}
      </div>
      <button
        type="button"
        data-testid="draw-color-eraser"
        aria-pressed={current === "eraser"}
        onClick={() => onSelect("eraser")}
        className={cn(
          "mt-2 flex w-full items-center justify-center gap-1.5 rounded-md border px-2 py-1.5 text-xs",
          current === "eraser" ? "ring-2 ring-primary" : "hover:bg-muted/50",
        )}
      >
        <Eraser className="h-3.5 w-3.5" />
        {t("drawEraser")}
      </button>
    </div>
  );
}
```

Adjust to `AVAILABLE_COLORS`/`getBoardColor`'s actual signatures after reading `web/src/lib/board-colors.ts`.

- [ ] **Step 4: i18n.** Add to `web/messages/en.json` under the existing `templateEditor` namespace (keep alphabetical-ish placement consistent with the file):

```json
"drawMode": "Draw on board",
"drawModeActive": "Exit drawing mode",
"drawBrush": "Drawing color",
"drawEraser": "Eraser",
"drawColors": {
  "red": "Red", "orange": "Orange", "yellow": "Yellow", "green": "Green",
  "blue": "Blue", "violet": "Violet", "white": "White", "black": "Black"
}
```

And under the `pageBuilder` namespace: `"drawModeHint": "Drawing mode is on — click or drag on the preview to paint tiles. Esc to exit."`. Translate all keys into the 13 other locale files (simple vocabulary; follow each file's existing tone). Verify no locale drift: every locale gets exactly the same key set.

- [ ] **Step 5: ToolbarDropdown props.** Read `ToolbarDropdown.tsx`; add optional `disabled?: boolean` and `"data-testid"?: string` props applied to the trigger button (disabled also prevents opening).
- [ ] **Step 6: Run tests → PASS. Prettier + commit** `feat(draw-mode): add draw color picker and i18n strings`.

---

### Task 5: Pencil toggle in the toolbar

**Files:**
- Modify: `web/src/components/tiptap-template-editor/components/TemplateEditorToolbar.tsx`
- Test: `web/src/__tests__/template-editor-toolbar-draw.test.tsx`

**Interfaces:**
- Consumes: `DrawColorPickerContent` (Task 4), `DrawBrush` (Task 1).
- Produces: new optional props on `TemplateEditorToolbar`:

```ts
drawMode?: boolean;
onDrawModeToggle?: () => void;
drawBrush?: DrawBrush;
onDrawBrushChange?: (brush: DrawBrush) => void;
```

Behavior:
1. When `onDrawModeToggle` is provided, render a pencil toggle button (lucide `Pencil`, `data-testid="draw-mode-toggle"`, `aria-pressed={drawMode}`, tooltip `t("drawMode")` / `t("drawModeActive")`) as the FIRST toolbar group, followed by a divider.
2. When `drawMode` is true, render next to the pencil a `ToolbarDropdown` (`data-testid="draw-brush-dropdown"`, label `t("drawBrush")`) whose icon is a 4×4 rounded swatch of the current brush color (or the `Eraser` icon when brush is `"eraser"`), containing `DrawColorPickerContent` (`onSelect` also closes the dropdown).
3. When `drawMode` is true, disable every content-editing control: cut/copy/paste buttons, variables/colors/formatting dropdowns (via the new `disabled` prop), formula button, wrap toggle, all three alignment buttons, and the sync-from-board button. Undo/redo stay enabled. Use `disabled` + the existing `opacity-60 cursor-not-allowed` classes.

- [ ] **Step 1: Failing test** — `web/src/__tests__/template-editor-toolbar-draw.test.tsx`. Render the toolbar directly with `editor={null}` and a QueryClientProvider (the toolbar uses `useQuery`; mock `api.getTemplateVariables` with `vi.mock("@/lib/api", ...)` returning `{ variables: { a: {} }, colors: { red: 63 }, formatting: {} }`):

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TemplateEditorToolbar } from "@/components/tiptap-template-editor/components/TemplateEditorToolbar";

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = (await importOriginal()) as Record<string, unknown>;
  return {
    ...mod,
    api: {
      ...(mod.api as Record<string, unknown>),
      getTemplateVariables: vi.fn().mockResolvedValue({ variables: { x: {} }, colors: { red: 63 }, formatting: {} }),
    },
  };
});

function renderToolbar(props: Record<string, unknown>) {
  const qc = new QueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <TemplateEditorToolbar editor={null} {...props} />
    </QueryClientProvider>,
  );
}

describe("TemplateEditorToolbar draw mode", () => {
  it("renders the pencil toggle and fires it", () => {
    const onDrawModeToggle = vi.fn();
    renderToolbar({ drawMode: false, onDrawModeToggle, drawBrush: "red", onDrawBrushChange: vi.fn() });
    const toggle = screen.getByTestId("draw-mode-toggle");
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(onDrawModeToggle).toHaveBeenCalled();
  });

  it("shows brush dropdown and disables editing controls in draw mode", () => {
    renderToolbar({ drawMode: true, onDrawModeToggle: vi.fn(), drawBrush: "red", onDrawBrushChange: vi.fn() });
    expect(screen.getByTestId("draw-mode-toggle")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("draw-brush-dropdown")).toBeInTheDocument();
    expect(screen.getByLabelText("Cut")).toBeDisabled();
    expect(screen.getByLabelText("Paste")).toBeDisabled();
  });

  it("hides the pencil when no handler is provided", () => {
    renderToolbar({});
    expect(screen.queryByTestId("draw-mode-toggle")).toBeNull();
  });
});
```

(Adjust aria-label matchers to the toolbar's actual labels — Cut/Copy/Paste use literal `aria-label="Cut"` etc. today.)

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** per the behavior list. Compute `const editingDisabled = !!drawMode;` and thread into each control's `disabled`/className. Follow the file's existing Tooltip + button structure exactly.
- [ ] **Step 4: Run → PASS. Prettier + commit** `feat(draw-mode): pencil toggle and brush picker in editor toolbar`.

---

### Task 6: Editor imperative paint API + collapse

**Files:**
- Modify: `web/src/components/tiptap-template-editor/TipTapTemplateEditor.tsx`
- Test: `web/src/__tests__/tiptap-editor-apply-stroke.test.tsx`

**Interfaces:**
- Consumes: `paintLine`, `CellPaint`, `DrawBrush` (Task 1); `parseTemplateSimple`, `serializeTemplateSimple` (existing); `closeHistory` from `@tiptap/pm/history`; toolbar props (Task 5).
- Produces (used by Task 7):

```ts
export interface StrokePaint { row: number; col: number }
export interface TipTapTemplateEditorHandle {
  /** Applies one stroke as ONE undo step. Returns affected row indices. */
  applyStroke(paints: StrokePaint[], color: BoardColorName | null): number[];
  undo(): void;
  redo(): void;
}
```

New props: `drawMode?: boolean`, `onDrawModeToggle?: () => void`, `drawBrush?: DrawBrush`, `onDrawBrushChange?: (b: DrawBrush) => void` — forwarded to `TemplateEditorToolbar`. When `drawMode`, the editor content container, line-number gutter, and line counter are hidden (`hidden` class — keep mounted), toolbar stays.

**Implementation notes:**
1. Convert the component to `forwardRef<TipTapTemplateEditorHandle, TipTapTemplateEditorProps>` and add `useImperativeHandle`.
2. Fix the ignored width prop: destructure `boardWidth = BOARD_WIDTH` (today it destructures `_boardWidth`, which never receives the passed `boardWidth={dims.cols}` — rename and use it in `applyStroke`).
3. `applyStroke` body:

```ts
applyStroke(paints, color) {
  const ed = editorRef.current;
  if (!ed || ed.isDestroyed) return [];
  const lines = serializeTemplateSimple(ed.getJSON(), boardLines).split("\n");
  const byRow = new Map<number, CellPaint[]>();
  for (const p of paints) {
    if (p.row < 0 || p.row >= boardLines || p.col < 0 || p.col >= boardWidth) continue;
    const arr = byRow.get(p.row) ?? [];
    arr.push({ col: p.col, color });
    byRow.set(p.row, arr);
  }
  if (byRow.size === 0) return [];
  while (lines.length < boardLines) lines.push("");
  for (const [row, rowPaints] of byRow) {
    lines[row] = paintLine(lines[row] ?? "", rowPaints, boardWidth);
  }
  const json = parseTemplateSimple(lines.join("\n"), boardLines);
  const paragraph = ed.schema.nodeFromJSON(json.content![0]);
  const { state, view } = ed;
  view.dispatch(closeHistory(state.tr.replaceWith(0, state.doc.content.size, paragraph)));
  return [...byRow.keys()].sort((a, b) => a - b);
}
```

`closeHistory` (import from `@tiptap/pm/history`) forces a history boundary so consecutive strokes within ProseMirror's 500ms `newGroupDelay` stay separate undo steps. The dispatch fires `onUpdate` → `onChange` synchronously, so the parent's `templateLines` update in the same event.
4. `undo()`/`redo()`: `editorRef.current?.chain().undo().run()` (no `.focus()` — draw mode must not focus a hidden editor).
5. Collapse: wrap the editor-container `<div className="flex-1">` content (border box + line counter) in `className={cn(..., drawMode && "hidden")}`.

- [ ] **Step 1: Failing test** — `web/src/__tests__/tiptap-editor-apply-stroke.test.tsx`. TipTap needs a real DOM; jsdom works (other editor tests exist — check `page-builder-device-switch.test.tsx` for any required setup/mocks and mirror it). Test through the ref:

```tsx
import { render, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

import type { TipTapTemplateEditorHandle } from "@/components/tiptap-template-editor/TipTapTemplateEditor";
import { TipTapTemplateEditor } from "@/components/tiptap-template-editor/TipTapTemplateEditor";

describe("TipTapTemplateEditor applyStroke", () => {
  async function setup(value: string) {
    const ref = createRef<TipTapTemplateEditorHandle>();
    const onChange = vi.fn();
    render(
      <TipTapTemplateEditor
        ref={ref}
        value={value}
        onChange={onChange}
        showToolbar={false}
        boardLines={6}
        boardWidth={22}
      />,
    );
    await waitFor(() => expect(ref.current).not.toBeNull());
    return { ref, onChange };
  }

  it("paints cells into template lines as one change", async () => {
    const { ref, onChange } = await setup("HELLO\n\n\n\n\n");
    const rows = ref.current!.applyStroke(
      [
        { row: 0, col: 1 },
        { row: 2, col: 0 },
      ],
      "blue",
    );
    expect(rows).toEqual([0, 2]);
    await waitFor(() => {
      const last = onChange.mock.calls.at(-1)![0] as string;
      expect(last.split("\n")[0]).toBe("H{{blue}}LLO");
      expect(last.split("\n")[2]).toBe("{{blue}}");
    });
  });

  it("strips variables on painted lines and undo restores them", async () => {
    const { ref, onChange } = await setup("HI {{weather.temp}}\n\n\n\n\n");
    ref.current!.applyStroke([{ row: 0, col: 0 }], "red");
    await waitFor(() => {
      expect((onChange.mock.calls.at(-1)![0] as string).split("\n")[0]).toBe("{{red}}I");
    });
    ref.current!.undo();
    await waitFor(() => {
      expect((onChange.mock.calls.at(-1)![0] as string).split("\n")[0]).toBe("HI {{weather.temp}}");
    });
  });

  it("two strokes are two undo steps", async () => {
    const { ref, onChange } = await setup("\n\n\n\n\n");
    ref.current!.applyStroke([{ row: 0, col: 0 }], "red");
    ref.current!.applyStroke([{ row: 0, col: 1 }], "green");
    ref.current!.undo();
    await waitFor(() => {
      expect((onChange.mock.calls.at(-1)![0] as string).split("\n")[0]).toBe("{{red}}");
    });
    ref.current!.undo();
    await waitFor(() => {
      expect((onChange.mock.calls.at(-1)![0] as string).split("\n")[0]).toBe("");
    });
  });
});
```

- [ ] **Step 2: Run → FAIL** (no ref support yet).
- [ ] **Step 3: Implement** per notes above. Also thread the four new draw props to `TemplateEditorToolbar`.
- [ ] **Step 4: Run new + existing editor-related unit tests → PASS.**
- [ ] **Step 5: Prettier + commit** `feat(draw-mode): imperative stroke API and collapse on TipTap editor`.

---

### Task 7: PageBuilder wiring

**Files:**
- Modify: `web/src/components/page-builder.tsx`
- Test: `web/src/__tests__/page-builder-draw-mode.test.tsx` (light — full interaction is covered by e2e)

**Interfaces:**
- Consumes: `TipTapTemplateEditorHandle`, `StrokePaint` (Task 6), `DrawableBoardPreview`, `StrokeCell` (Task 3), `DrawBrush`, `paintLine`, `isPositionalLine`, `renderPositionalLine` (Task 1).
- Produces: user-facing behavior; no new exports.

**Implementation (all in `page-builder.tsx`):**

1. State (near the `editorMode` state, ~line 155):

```ts
const [drawMode, setDrawMode] = useState(false);
const [drawBrush, setDrawBrush] = useState<DrawBrush>("red");
const [strokePreviewCells, setStrokePreviewCells] = useState<StrokeCell[]>([]);
const tipTapRef = useRef<TipTapTemplateEditorHandle>(null);
```

2. Force draw mode off when leaving rich mode or switching device type: add `setDrawMode(false)` inside `handleEditorModeChange` (~line 375) and in the device `Select`'s `onValueChange` (~line 1483).

3. Stroke commit handler (define near the other callbacks):

```ts
const handleStrokeCommit = useCallback(
  (cells: StrokeCell[]) => {
    setStrokePreviewCells([]);
    const color = drawBrush === "eraser" ? null : drawBrush;
    const rows = tipTapRef.current?.applyStroke(cells, color) ?? [];
    if (rows.length === 0) return;
    // Painted lines are positional: force left alignment + wrap off.
    setLineAlignments((prev) => {
      const next = [...prev];
      for (const r of rows) next[r] = "left";
      return next;
    });
    setLineWrapEnabled((prev) => {
      const next = [...prev];
      for (const r of rows) next[r] = false;
      return next;
    });
  },
  [drawBrush],
);
```

4. Draw-mode preview composition (client-side, instant — no server round-trip for painted rows):

```ts
const drawPreviewMessage = useMemo(() => {
  if (!drawMode) return null;
  const serverLines = (preview ?? lastPreview ?? "").split("\n");
  const strokeByRow = new Map<number, CellPaint[]>();
  const strokeColor = drawBrush === "eraser" ? null : drawBrush;
  for (const c of strokePreviewCells) {
    const arr = strokeByRow.get(c.row) ?? [];
    arr.push({ col: c.col, color: strokeColor });
    strokeByRow.set(c.row, arr);
  }
  const out: string[] = [];
  for (let r = 0; r < dims.rows; r++) {
    const tpl = templateLines[r] ?? "";
    const strokePaints = strokeByRow.get(r);
    const isLocallyRenderable =
      isPositionalLine(tpl) && (lineAlignments[r] ?? "left") === "left" && !(lineWrapEnabled[r] ?? false);
    if (strokePaints) {
      // Preview exactly what committing this stroke will produce
      // (including variable stripping + left alignment).
      out.push(renderPositionalLine(paintLine(tpl, strokePaints, dims.cols)));
    } else if (isLocallyRenderable) {
      out.push(renderPositionalLine(tpl));
    } else {
      out.push(serverLines[r] ?? "");
    }
  }
  return out.join("\n");
}, [drawMode, strokePreviewCells, drawBrush, templateLines, lineAlignments, lineWrapEnabled, preview, lastPreview, dims.rows, dims.cols]);
```

(`CellPaint` imported from the draw-mode utils.)

5. Keyboard shortcuts while drawing (Esc exits; undo/redo work with the editor blurred):

```ts
useEffect(() => {
  if (!drawMode) return;
  const onKey = (e: KeyboardEvent) => {
    const target = e.target as HTMLElement | null;
    if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) return;
    if (e.key === "Escape") {
      setDrawMode(false);
      return;
    }
    if (!(e.metaKey || e.ctrlKey)) return;
    const k = e.key.toLowerCase();
    if (k === "z" && !e.shiftKey) {
      e.preventDefault();
      tipTapRef.current?.undo();
    } else if (k === "y" || (k === "z" && e.shiftKey)) {
      e.preventDefault();
      tipTapRef.current?.redo();
    }
  };
  window.addEventListener("keydown", onKey);
  return () => window.removeEventListener("keydown", onKey);
}, [drawMode]);
```

6. Editor props (rich branch, ~line 1356): add `ref={tipTapRef}`, `drawMode={drawMode}`, `onDrawModeToggle={() => setDrawMode((v) => !v)}`, `drawBrush={drawBrush}`, `onDrawBrushChange={setDrawBrush}`.

7. Preview (~line 1525): wrap `ScaledBoardDisplay` and override props in draw mode:

```tsx
<DrawableBoardPreview active={drawMode} onStrokePreview={setStrokePreviewCells} onStrokeCommit={handleStrokeCommit}>
  <ScaledBoardDisplay
    message={drawMode ? drawPreviewMessage : /* existing IIFE unchanged */}
    isLoading={drawMode ? false : /* existing IIFE unchanged */}
    isStatic={drawMode}
    size="md"
    boardType={effectiveBoardColor}
    deviceType={deviceType}
    notesWide={notesWide}
    notesTall={notesTall}
  />
</DrawableBoardPreview>
{drawMode && (
  <p className="mt-1 text-center text-xs text-muted-foreground">{t("drawModeHint")}</p>
)}
```

Confirm `BoardDisplay` accepts `isStatic` through `ScaledBoardDisplay` (it does — `ComponentProps<typeof BoardDisplay>` passthrough).

- [ ] **Step 1: Failing test** — `web/src/__tests__/page-builder-draw-mode.test.tsx`: mirror the render setup of `page-builder-device-switch.test.tsx` (providers, api mocks). Assert: (a) pencil toggle visible in rich mode; (b) clicking it hides `.ProseMirror`'s container (query `[role="textbox"]` is in a `hidden` ancestor / not visible) and shows the draw surface `[data-draw-surface="true"]`; (c) pressing Escape exits (toggle `aria-pressed` back to false, textbox visible again).
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement per the numbered notes. Run → PASS.**
- [ ] **Step 4: Run the full web unit suite** `... npx vitest run` → no regressions.
- [ ] **Step 5: Typecheck**: `docker compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm run typecheck"` → clean.
- [ ] **Step 6: Prettier + commit** `feat(draw-mode): wire pencil drawing into page builder preview`.

---

### Task 8: E2E — draw-mode.spec.ts

**Files:**
- Create: `web/tests/draw-mode.spec.ts`

**Prep:** Rebuild + start the dev container so the UI includes Tasks 1-7 (`docker compose -f docker-compose.dev.yml build && docker compose -f docker-compose.dev.yml up -d`; verify with `docker inspect` that the running container's mounts point at THIS worktree). Run with `cd web && BASE_URL=http://localhost:4420 npx playwright test tests/draw-mode.spec.ts` — Playwright itself runs on the host (existing repo practice for e2e; it drives the containerized app).

**Read first:** `web/tests/helpers.ts` (fixtures/`test` export, `configureBoard`, `createPage`, `setActivePage`, `getMockBoardState`, `suppressWizard`), `web/tests/page-builder.spec.ts` (save-button selectors, navigation patterns), `web/tests/note-array-local.spec.ts` (note-array board setup via `configureMockCloud`).

**Test cases (follow existing spec structure — `test` from `./helpers`):**

1. **Paint and save (flagship):** goto `/pages/new` (with `suppressWizard`), click `draw-mode-toggle`, assert the editor textbox is hidden and `[data-draw-surface="true"]` is present; open `draw-brush-dropdown`, click `draw-color-blue`; click tiles `[data-row="1"][data-col="3"]` and `[data-row="4"][data-col="0"]`; assert both have `data-cell-value="blue"` (in draw mode the composed preview uses named markers `{blue}`, so the color token's `code` — what `getCharFromToken` returns — is the name string); exit draw mode with Escape; fill the page name; save; then `setActivePage(id)` and `expect.poll(getMockBoardState)` until `characters[1][3] === 67`.
2. **Drag stroke + single undo:** enter draw mode, pick red, `page.mouse` down on `[data-row="2"][data-col="2"]` center, move through cols 3-6 (use `boundingBox()` centers, `steps: 3`), up; assert cols 2-6 painted; press `ControlOrMeta+z` once; assert ALL five cells reverted.
3. **Eraser:** paint 2 cells, switch brush to `draw-color-eraser`, click one painted cell; assert it reverted to blank while the other stays painted.
4. **Variable stripping + undo:** `createPage("Draw Var", ["HI {{date_time.time}}", "", "", "", "", ""])`, goto `/pages/edit/<id>`, enter draw mode, paint `[data-row="0"][data-col="0"]`; assert the (hidden) editor contains zero `[data-type="variable"]` elements; undo (`ControlOrMeta+z`); assert the variable node is back and the painted cell reverted.
5. **Toolbar lockout:** in draw mode, assert Cut/Paste buttons and alignment buttons are disabled and the variables dropdown trigger is disabled; exit draw mode; assert re-enabled.
6. **Note device:** `createPage("Note Draw", ["", "", ""], "note")`, edit it, paint a cell at `[data-row="2"][data-col="14"]` (bottom-right of 3×15), assert painted — proves bounds work on small boards.
7. **Note array:** mirror `note-array-local.spec.ts` setup (`configureMockCloud(2, 1)` + board config), open the note-array page editor, paint a cell with col ≥ 15 (i.e. in the second note, e.g. `[data-row="1"][data-col="20"]`), assert painted — proves the 6×30-cell composite grid paints beyond single-note bounds.

- [ ] **Step 1: Write the spec** with the cases above.
- [ ] **Step 2: Run it** against the rebuilt container → all pass. Iterate on selectors if the app markup differs; fix product code only if a real bug surfaces (systematic-debugging skill).
- [ ] **Step 3: Run neighboring suites for regressions:** `npx playwright test tests/page-builder.spec.ts tests/note-pages.spec.ts tests/draw-mode.spec.ts`.
- [ ] **Step 4: Prettier + commit** `test(draw-mode): e2e coverage for pencil drawing`.

---

### Task 9: Video proof

**Files:**
- Create: `web/playwright-video.config.ts`
- Create: `web/tests/draw-mode-demo.spec.ts`
- Modify: `web/playwright.config.ts` — always exclude the demo spec from the main suite:

```ts
testIgnore: [...(process.env.CI ? ciIgnore : []), "**/draw-mode-demo.spec.ts"],
```

- [ ] **Step 1: Config** — copy the shape of `playwright-screenshots.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  testMatch: "draw-mode-demo.spec.ts",
  outputDir: "./draw-mode-demo-results",
  fullyParallel: false,
  retries: 0,
  workers: 1,
  reporter: "list",
  timeout: 180_000,
  globalSetup: "./tests/global-setup.ts",
  use: {
    baseURL: process.env.BASE_URL || "http://localhost:4420",
    trace: "off",
    screenshot: "off",
    viewport: { width: 1280, height: 800 },
    video: { mode: "on", size: { width: 1280, height: 800 } },
  },
  projects: [{ name: "draw-demo", use: { ...devices["Desktop Chrome"] } }],
});
```

- [ ] **Step 2: Demo spec** — one test walking the whole feature at a human pace (`page.waitForTimeout(400-800)` between beats; this is a demo, not a regression test): open `/pages/new` → toggle pencil → pick red → draw a small heart shape by clicking ~10 cells → drag a yellow underline across row 5 → erase two cells → undo → redo → Escape → show restored editor with the color chips in the template → save the page → `setActivePage` → end on the pages list. Use the same helpers/fixtures as Task 8.
- [ ] **Step 3: Record:** `cd web && npx playwright test --config playwright-video.config.ts`. Find the `.webm` under `web/draw-mode-demo-results/**/video.webm` and copy it to the session scratchpad plus report its path to the user.
- [ ] **Step 4: gitignore check:** ensure `draw-mode-demo-results/` is ignored (add to `web/.gitignore` if playwright results aren't already covered).
- [ ] **Step 5: Prettier + commit** `test(draw-mode): video demo spec and config`.

---

### Task 10: Full verification + PR

- [ ] Web unit suite: `docker compose -f docker-compose.dev.yml run --rm --profile test web sh -c "npm ci && npm run test:run"` → green.
- [ ] Lint + format + typecheck: `sh -c "npm ci && npm run lint && npm run format:check && npm run typecheck"` in the web test container → green.
- [ ] Python tests unaffected (no `src/` Python changes) — skip unless something touched them.
- [ ] E2E: full draw spec + neighbors (Task 8 Step 3 command) against a freshly rebuilt container.
- [ ] i18n audit: every locale file has the new keys (`grep -l "drawEraser" web/messages/*.json | wc -l` → 14).
- [ ] Verify no stray root-level `.md` files; scratch files only in scratchpad.
- [ ] Push branch, open PR to `main` titled `feat: pencil draw mode on the board preview` with a summary, screenshots/video pointer, and test evidence. Body ends with the standard generation footer.
