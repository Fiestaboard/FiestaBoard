"use client";

import { useTranslations } from "@/i18n/translations";
import { type KeyboardEvent, useEffect, useRef, useState } from "react";

import { Badge } from "@/components/ui/badge";
import type { DayPattern } from "@/lib/api";
import { cn } from "@/lib/utils";

const PATTERNS: DayPattern[] = ["all", "weekdays", "weekends", "custom"];

interface DaySelectorProps {
  value: DayPattern;
  customDays?: string[];
  onChange: (pattern: DayPattern, customDays?: string[]) => void;
  className?: string;
}

const WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday"];
const WEEKENDS = ["saturday", "sunday"];
const ALL_DAYS = [...WEEKDAYS, ...WEEKENDS];

export function DaySelector({ value, customDays = [], onChange, className }: DaySelectorProps) {
  const t = useTranslations("daySelector");
  const dayLabels = t.raw("dayLabels") as Record<string, string>;
  const [selectedCustomDays, setSelectedCustomDays] = useState<string[]>(customDays);
  const radioRefs = useRef<Record<DayPattern, HTMLButtonElement | null>>({
    all: null,
    weekdays: null,
    weekends: null,
    custom: null,
  });

  const handleRadioKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!["ArrowDown", "ArrowRight", "ArrowUp", "ArrowLeft", "Home", "End"].includes(e.key)) {
      return;
    }
    e.preventDefault();
    const currentIndex = PATTERNS.indexOf(value);
    let nextIndex: number;
    if (e.key === "Home") {
      nextIndex = 0;
    } else if (e.key === "End") {
      nextIndex = PATTERNS.length - 1;
    } else if (e.key === "ArrowDown" || e.key === "ArrowRight") {
      nextIndex = (currentIndex + 1) % PATTERNS.length;
    } else {
      nextIndex = (currentIndex - 1 + PATTERNS.length) % PATTERNS.length;
    }
    const nextPattern = PATTERNS[nextIndex];
    handlePatternChange(nextPattern);
    radioRefs.current[nextPattern]?.focus();
  };

  // Update selectedCustomDays when customDays prop changes
  useEffect(() => {
    setSelectedCustomDays(customDays);
  }, [customDays]);

  const handlePatternChange = (pattern: DayPattern) => {
    if (pattern === "custom") {
      onChange(pattern, selectedCustomDays.length > 0 ? selectedCustomDays : ["monday"]);
    } else {
      onChange(pattern, undefined);
    }
  };

  const handleCustomDayToggle = (day: string) => {
    const newCustomDays = selectedCustomDays.includes(day)
      ? selectedCustomDays.filter((d) => d !== day)
      : [...selectedCustomDays, day];

    // Ensure at least one day is selected
    if (newCustomDays.length > 0) {
      setSelectedCustomDays(newCustomDays);
      onChange("custom", newCustomDays);
    }
  };

  return (
    <fieldset className={cn("space-y-3 border-none p-0 m-0", className)}>
      <legend className="text-sm font-medium leading-none">{t("daysLegend")}</legend>

      {/* Pattern Radio Buttons */}
      <div
        className="flex flex-col gap-2"
        role="radiogroup"
        aria-label={t("dayPatternAriaLabel")}
        onKeyDown={handleRadioKeyDown}
      >
        <button
          type="button"
          role="radio"
          aria-checked={value === "all"}
          tabIndex={value === "all" ? 0 : -1}
          ref={(el) => {
            radioRefs.current.all = el;
          }}
          onClick={() => handlePatternChange("all")}
          className={cn(
            "flex items-center gap-2 rounded-lg border px-4 py-3 text-left transition-colors",
            value === "all" ? "border-primary bg-primary/5 text-primary" : "border-border hover:bg-accent",
          )}
        >
          <div
            className={cn(
              "h-4 w-4 rounded-full border-2 flex items-center justify-center",
              value === "all" ? "border-primary" : "border-muted-foreground",
            )}
          >
            {value === "all" && <div className="h-2 w-2 rounded-full bg-primary" />}
          </div>
          <span className="text-sm font-medium">{t("allDays")}</span>
          <div className="ml-auto flex gap-1">
            {ALL_DAYS.map((day) => (
              <Badge key={day} variant="secondary" className="text-xs">
                {dayLabels[day]}
              </Badge>
            ))}
          </div>
        </button>

        <button
          type="button"
          role="radio"
          aria-checked={value === "weekdays"}
          tabIndex={value === "weekdays" ? 0 : -1}
          ref={(el) => {
            radioRefs.current.weekdays = el;
          }}
          onClick={() => handlePatternChange("weekdays")}
          className={cn(
            "flex items-center gap-2 rounded-lg border px-4 py-3 text-left transition-colors",
            value === "weekdays" ? "border-primary bg-primary/5 text-primary" : "border-border hover:bg-accent",
          )}
        >
          <div
            className={cn(
              "h-4 w-4 rounded-full border-2 flex items-center justify-center",
              value === "weekdays" ? "border-primary" : "border-muted-foreground",
            )}
          >
            {value === "weekdays" && <div className="h-2 w-2 rounded-full bg-primary" />}
          </div>
          <span className="text-sm font-medium">{t("weekdays")}</span>
          <div className="ml-auto flex gap-1">
            {WEEKDAYS.map((day) => (
              <Badge key={day} variant="secondary" className="text-xs">
                {dayLabels[day]}
              </Badge>
            ))}
          </div>
        </button>

        <button
          type="button"
          role="radio"
          aria-checked={value === "weekends"}
          tabIndex={value === "weekends" ? 0 : -1}
          ref={(el) => {
            radioRefs.current.weekends = el;
          }}
          onClick={() => handlePatternChange("weekends")}
          className={cn(
            "flex items-center gap-2 rounded-lg border px-4 py-3 text-left transition-colors",
            value === "weekends" ? "border-primary bg-primary/5 text-primary" : "border-border hover:bg-accent",
          )}
        >
          <div
            className={cn(
              "h-4 w-4 rounded-full border-2 flex items-center justify-center",
              value === "weekends" ? "border-primary" : "border-muted-foreground",
            )}
          >
            {value === "weekends" && <div className="h-2 w-2 rounded-full bg-primary" />}
          </div>
          <span className="text-sm font-medium">{t("weekends")}</span>
          <div className="ml-auto flex gap-1">
            {WEEKENDS.map((day) => (
              <Badge key={day} variant="secondary" className="text-xs">
                {dayLabels[day]}
              </Badge>
            ))}
          </div>
        </button>

        <button
          type="button"
          role="radio"
          aria-checked={value === "custom"}
          tabIndex={value === "custom" ? 0 : -1}
          ref={(el) => {
            radioRefs.current.custom = el;
          }}
          onClick={() => handlePatternChange("custom")}
          className={cn(
            "flex items-center gap-2 rounded-lg border px-4 py-3 text-left transition-colors",
            value === "custom" ? "border-primary bg-primary/5 text-primary" : "border-border hover:bg-accent",
            value === "custom" && "rounded-b-none border-b-0",
          )}
        >
          <div
            className={cn(
              "h-4 w-4 rounded-full border-2 flex items-center justify-center",
              value === "custom" ? "border-primary" : "border-muted-foreground",
            )}
          >
            {value === "custom" && <div className="h-2 w-2 rounded-full bg-primary" />}
          </div>
          <span className="text-sm font-medium">{t("customDays")}</span>
        </button>

        {value === "custom" && (
          <div
            className="ml-6 flex flex-wrap gap-2 px-4 pb-3 pt-2 border border-t-0 border-primary bg-primary/5 rounded-b-lg"
            role="group"
            aria-label={t("selectCustomDaysAriaLabel")}
          >
            {ALL_DAYS.map((day) => (
              <label
                key={day}
                className={cn(
                  "rounded-md border px-3 py-1.5 text-xs font-medium transition-colors cursor-pointer inline-flex items-center gap-1.5",
                  selectedCustomDays.includes(day)
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-background hover:bg-accent",
                )}
              >
                <input
                  type="checkbox"
                  checked={selectedCustomDays.includes(day)}
                  onChange={() => handleCustomDayToggle(day)}
                  className="sr-only"
                  aria-label={day.charAt(0).toUpperCase() + day.slice(1)}
                />
                {dayLabels[day]}
              </label>
            ))}
          </div>
        )}
      </div>
    </fieldset>
  );
}
