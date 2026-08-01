/**
 * Color Picker Content - Compact color grid for toolbar
 */
"use client";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@fiestaboard/ui";
import { Heart } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { DeviceType } from "@/lib/api";
import { FIESTABOARD_COLORS } from "@/lib/board-colors";
import { cn } from "@/lib/utils";

interface ColorPickerContentProps {
  onInsert: (colorValue: string) => void;
  deviceType?: DeviceType;
}

const COLOR_MAP: Record<string, { bg: string; needsDarkText: boolean }> = {
  red: { bg: FIESTABOARD_COLORS.red, needsDarkText: false },
  orange: { bg: FIESTABOARD_COLORS.orange, needsDarkText: false },
  yellow: { bg: FIESTABOARD_COLORS.yellow, needsDarkText: true },
  green: { bg: FIESTABOARD_COLORS.green, needsDarkText: true },
  blue: { bg: FIESTABOARD_COLORS.blue, needsDarkText: false },
  violet: { bg: FIESTABOARD_COLORS.violet, needsDarkText: false },
  white: { bg: FIESTABOARD_COLORS.white, needsDarkText: true },
  black: { bg: FIESTABOARD_COLORS.black, needsDarkText: false },
};

const COLOR_ORDER = ["red", "orange", "yellow", "green", "blue", "violet", "white", "black"] as const;

export function ColorPickerContent({ onInsert, deviceType }: ColorPickerContentProps) {
  const isNote = deviceType === "note";
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const containerRef = useRef<HTMLDivElement>(null);
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // Handle keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!containerRef.current) return;

      // Only handle if focus is within the container or on a button
      const activeElement = document.activeElement;
      if (!containerRef.current.contains(activeElement) && activeElement !== containerRef.current) {
        return;
      }

      if (e.key === "ArrowDown") {
        e.preventDefault();
        setHighlightedIndex((prev) => {
          const newIndex = prev < COLOR_ORDER.length - 1 ? prev + 1 : 0;
          // Scroll highlighted item into view after state update
          setTimeout(() => {
            const highlightedElement = buttonRefs.current[newIndex];
            if (highlightedElement) {
              highlightedElement.scrollIntoView({ block: "nearest", behavior: "smooth" });
              highlightedElement.focus();
            }
          }, 0);
          return newIndex;
        });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setHighlightedIndex((prev) => {
          const newIndex = prev > 0 ? prev - 1 : COLOR_ORDER.length - 1;
          // Scroll highlighted item into view after state update
          setTimeout(() => {
            const highlightedElement = buttonRefs.current[newIndex];
            if (highlightedElement) {
              highlightedElement.scrollIntoView({ block: "nearest", behavior: "smooth" });
              highlightedElement.focus();
            }
          }, 0);
          return newIndex;
        });
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        setHighlightedIndex((prev) => {
          // Move to next item (wrapping at end)
          const newIndex = prev < COLOR_ORDER.length - 1 ? prev + 1 : 0;
          setTimeout(() => {
            const highlightedElement = buttonRefs.current[newIndex];
            if (highlightedElement) {
              highlightedElement.scrollIntoView({ block: "nearest", behavior: "smooth" });
              highlightedElement.focus();
            }
          }, 0);
          return newIndex;
        });
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        setHighlightedIndex((prev) => {
          // Move to previous item (wrapping at start)
          const newIndex = prev > 0 ? prev - 1 : COLOR_ORDER.length - 1;
          setTimeout(() => {
            const highlightedElement = buttonRefs.current[newIndex];
            if (highlightedElement) {
              highlightedElement.scrollIntoView({ block: "nearest", behavior: "smooth" });
              highlightedElement.focus();
            }
          }, 0);
          return newIndex;
        });
      } else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < COLOR_ORDER.length) {
          const colorName = COLOR_ORDER[highlightedIndex];
          onInsert(`{{${colorName}}}`);
        } else if (COLOR_ORDER.length > 0) {
          // Select first item if nothing highlighted
          const colorName = COLOR_ORDER[0];
          onInsert(`{{${colorName}}}`);
        }
      }
    };

    const container = containerRef.current;
    if (container) {
      container.addEventListener("keydown", handleKeyDown);
      return () => {
        container.removeEventListener("keydown", handleKeyDown);
      };
    }
  }, [highlightedIndex, onInsert]);

  // Reset highlighted index when component mounts or when focus enters
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleFocusIn = () => {
      // When focus enters the container, highlight the first item if nothing is highlighted
      if (highlightedIndex === -1 && COLOR_ORDER.length > 0) {
        setHighlightedIndex(0);
        setTimeout(() => {
          const firstButton = buttonRefs.current[0];
          if (firstButton) {
            firstButton.focus();
          }
        }, 0);
      }
    };

    container.addEventListener("focusin", handleFocusIn);
    return () => {
      container.removeEventListener("focusin", handleFocusIn);
    };
  }, [highlightedIndex]);

  return (
    <TooltipProvider>
      <div
        ref={containerRef}
        className={cn("p-2", !isNote && "pb-1")}
        tabIndex={0}
        role="listbox"
        aria-label="Color picker"
      >
        <div className="grid grid-cols-4 gap-2 w-64">
          {COLOR_ORDER.map((colorName, index) => {
            const colorInfo = COLOR_MAP[colorName];
            if (!colorInfo) return null;

            const isHighlighted = highlightedIndex === index;

            return (
              <Tooltip key={colorName}>
                <TooltipTrigger asChild>
                  <button
                    ref={(el) => {
                      buttonRefs.current[index] = el;
                    }}
                    type="button"
                    onClick={() => onInsert(`{{${colorName}}}`)}
                    onFocus={() => setHighlightedIndex(index)}
                    style={{ backgroundColor: colorInfo.bg }}
                    className={cn(
                      "h-10 rounded-md text-xs font-medium transition-all hover:scale-105 hover:shadow-md",
                      "flex items-center justify-center focus:outline-none",
                      isHighlighted && "ring-2 ring-offset-2 ring-primary scale-105 shadow-md",
                      colorInfo.needsDarkText ? "text-black/80" : "text-white/90",
                    )}
                    aria-label={`${colorName} color`}
                    role="option"
                    aria-selected={isHighlighted}
                  >
                    {colorName}
                  </button>
                </TooltipTrigger>
                <TooltipContent>
                  <p>{colorName}</p>
                </TooltipContent>
              </Tooltip>
            );
          })}
        </div>
        {isNote && (
          <div className="mt-2 pt-2 border-t border-border">
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  type="button"
                  onClick={() => onInsert("°")} // Degree symbol (°) renders as heart (❤) on Note device (code 62)
                  className={cn(
                    "w-full h-10 rounded-md text-sm font-medium transition-all hover:scale-[1.02] hover:shadow-md",
                    "flex items-center justify-center gap-1.5 focus:outline-none",
                    "bg-red-500/10 text-red-500 border border-red-500/20 hover:bg-red-500/20",
                  )}
                  aria-label="Heart character"
                  role="option"
                  aria-selected={false}
                >
                  <Heart className="w-4 h-4 fill-current" />
                  <span>heart</span>
                </button>
              </TooltipTrigger>
              <TooltipContent>
                <p>Insert heart character (Note only)</p>
              </TooltipContent>
            </Tooltip>
          </div>
        )}
      </div>
    </TooltipProvider>
  );
}
