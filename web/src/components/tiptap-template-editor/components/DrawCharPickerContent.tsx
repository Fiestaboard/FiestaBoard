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
    <div className="p-2">
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
