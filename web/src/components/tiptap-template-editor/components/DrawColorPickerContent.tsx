/**
 * Draw Color Picker Content - Brush color grid + eraser for draw mode
 */
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
            onClick={() => onSelect(name)}
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
