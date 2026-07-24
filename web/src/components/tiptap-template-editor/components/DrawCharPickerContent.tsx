/**
 * Draw Char Picker Content - Stamp-character grid for draw mode
 */
"use client";

import { cn } from "@/lib/utils";

import type { DrawBrush } from "../utils/draw-mode";
import { DRAW_CHARS } from "../utils/draw-mode";

interface DrawCharPickerContentProps {
  current: DrawBrush;
  onSelect: (brush: DrawBrush) => void;
}

export function DrawCharPickerContent({ current, onSelect }: DrawCharPickerContentProps) {
  const selectedChar = current.kind === "char" ? current.char : null;

  return (
    // w-64 matters: the dropdown panel is absolutely positioned inside a
    // trigger-sized wrapper, so without an explicit width the panel
    // shrink-fits to ~36px and the grid-cols-8 tracks (minmax(0,1fr))
    // collapse until the glyph buttons overlap.
    <div className="w-64 p-2" data-testid="draw-char-picker">
      <div className="grid grid-cols-8 gap-1">
        {DRAW_CHARS.map((char) => (
          <button
            key={char}
            type="button"
            data-draw-char={char}
            aria-pressed={selectedChar === char}
            aria-label={char}
            onClick={() => onSelect({ kind: "char", char })}
            className={cn(
              "flex h-7 w-7 items-center justify-center rounded border font-mono text-sm transition-shadow",
              selectedChar === char ? "ring-2 ring-primary ring-offset-1" : "hover:bg-muted/50",
            )}
          >
            {char}
          </button>
        ))}
      </div>
    </div>
  );
}
