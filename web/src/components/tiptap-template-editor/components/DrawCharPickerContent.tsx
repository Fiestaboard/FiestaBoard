/**
 * Draw Char Picker Content - Stamp-character grid for draw mode
 */
"use client";

import { useRef, useState } from "react";

import { cn } from "@/lib/utils";

import type { DrawBrush } from "../utils/draw-mode";
import { DRAW_CHARS } from "../utils/draw-mode";

interface DrawCharPickerContentProps {
  current: DrawBrush;
  onSelect: (brush: DrawBrush) => void;
}

const GRID_COLS = 8;

export function DrawCharPickerContent({ current, onSelect }: DrawCharPickerContentProps) {
  const selectedChar = current.kind === "char" ? current.char : null;
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([]);
  // Roving tabindex: exactly one button is in the tab order (the selected
  // character if any, otherwise the first), arrow keys move focus.
  const [focusedIndex, setFocusedIndex] = useState(() => {
    const selectedIndex = selectedChar ? DRAW_CHARS.indexOf(selectedChar) : -1;
    return selectedIndex >= 0 ? selectedIndex : 0;
  });

  const moveFocus = (index: number) => {
    const wrapped = ((index % DRAW_CHARS.length) + DRAW_CHARS.length) % DRAW_CHARS.length;
    setFocusedIndex(wrapped);
    buttonRefs.current[wrapped]?.focus();
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    switch (event.key) {
      case "ArrowRight":
        event.preventDefault();
        moveFocus(index + 1);
        break;
      case "ArrowLeft":
        event.preventDefault();
        moveFocus(index - 1);
        break;
      case "ArrowDown":
        event.preventDefault();
        moveFocus(index + GRID_COLS);
        break;
      case "ArrowUp":
        event.preventDefault();
        moveFocus(index - GRID_COLS);
        break;
      case "Home":
        event.preventDefault();
        moveFocus(0);
        break;
      case "End":
        event.preventDefault();
        moveFocus(DRAW_CHARS.length - 1);
        break;
    }
  };

  return (
    // w-64 matters: the dropdown panel is absolutely positioned inside a
    // trigger-sized wrapper, so without an explicit width the panel
    // shrink-fits to ~36px and the grid-cols-8 tracks (minmax(0,1fr))
    // collapse until the glyph buttons overlap.
    <div className="w-64 p-2" data-testid="draw-char-picker">
      <div className="grid grid-cols-8 gap-1">
        {DRAW_CHARS.map((char, index) => (
          <button
            key={char}
            ref={(el) => {
              buttonRefs.current[index] = el;
            }}
            type="button"
            data-draw-char={char}
            tabIndex={index === focusedIndex ? 0 : -1}
            aria-pressed={selectedChar === char}
            aria-label={char}
            onClick={() => onSelect({ kind: "char", char })}
            onFocus={() => setFocusedIndex(index)}
            onKeyDown={(event) => handleKeyDown(event, index)}
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
