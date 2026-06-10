"use client";

import { Check, ChevronsUpDown } from "lucide-react";
import type { CSSProperties } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useTranslations } from "@/i18n/translations";
import { ALL_TIMEZONES } from "@/lib/timezone-utils";
import { cn } from "@/lib/utils";

interface TimezonePickerProps {
  value: string;
  onChange: (timezone: string) => void;
  className?: string;
  disabled?: boolean;
  onValidationChange?: (isValid: boolean) => void;
  id?: string;
}

export function TimezonePicker({ value, onChange, className, disabled, onValidationChange, id }: TimezonePickerProps) {
  const t = useTranslations("timezonePicker");
  const [searchQuery, setSearchQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const [dropdownStyle, setDropdownStyle] = useState<CSSProperties>({});
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Find the display label for the current value
  const _currentLabel = useMemo(() => {
    const tz = ALL_TIMEZONES.find((t) => t.value === value);
    return tz ? tz.label : value;
  }, [value]);

  // Filter timezones based on search query
  const filteredTimezones = useMemo(() => {
    if (!searchQuery.trim()) {
      return ALL_TIMEZONES;
    }

    const query = searchQuery.toLowerCase();
    return ALL_TIMEZONES.filter(
      (tz) =>
        tz.value.toLowerCase().includes(query) ||
        tz.label.toLowerCase().includes(query) ||
        tz.offset.toLowerCase().includes(query),
    );
  }, [searchQuery]);

  // Reset highlighted index when filtered results change
  useEffect(() => {
    setHighlightedIndex(-1);
  }, [filteredTimezones]);

  // Check if current value is valid
  const isValid = useMemo(() => {
    if (!value) return true; // Empty is valid (will use default)
    return ALL_TIMEZONES.some((tz) => tz.value === value);
  }, [value]);

  // Notify parent of validation state
  useEffect(() => {
    onValidationChange?.(isValid);
  }, [isValid, onValidationChange]);

  // Update search query when value changes externally
  useEffect(() => {
    if (value && !isOpen) {
      const tz = ALL_TIMEZONES.find((t) => t.value === value);
      if (tz) {
        setSearchQuery(tz.label);
      } else {
        setSearchQuery(value);
      }
    }
  }, [value, isOpen]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      const inContainer = containerRef.current?.contains(target);
      const inList = listRef.current?.contains(target);
      if (!inContainer && !inList) {
        setIsOpen(false);
        setHighlightedIndex(-1);
        // Reset search query to current label when closing
        const tz = ALL_TIMEZONES.find((t) => t.value === value);
        setSearchQuery(tz ? tz.label : value);
      }
    };

    const handleScroll = (event: Event) => {
      // Don't reposition when the scroll is happening inside the dropdown list itself
      if (listRef.current?.contains(event.target as Node)) {
        return;
      }
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        const dropdownMaxHeight = 240;
        const spaceBelow = window.innerHeight - rect.bottom;
        const top =
          spaceBelow >= dropdownMaxHeight || spaceBelow >= rect.top
            ? rect.bottom + 4
            : rect.top - dropdownMaxHeight - 4;
        setDropdownStyle({
          position: "fixed",
          top,
          left: rect.left,
          width: rect.width,
          zIndex: 9999,
          pointerEvents: "auto",
        });
      }
    };

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      // Reposition dropdown when any ancestor scrolls (e.g. Sheet with overflow-y-auto)
      document.addEventListener("scroll", handleScroll, true);
      return () => {
        document.removeEventListener("mousedown", handleClickOutside);
        document.removeEventListener("scroll", handleScroll, true);
      };
    }
  }, [isOpen, value]);

  // Prevent Radix scroll-lock (react-remove-scroll) from blocking wheel events inside
  // the portal dropdown. The Sheet/Dialog modal adds a document-level wheel listener
  // that calls preventDefault() on events outside the modal DOM tree. Our portal is
  // appended to document.body, so react-remove-scroll treats it as "outside".
  // Stopping propagation on the list element prevents the event from reaching document.
  useEffect(() => {
    const el = listRef.current;
    if (!el || !isOpen) return;
    const handleWheel = (e: WheelEvent) => {
      e.stopPropagation();
    };
    el.addEventListener("wheel", handleWheel);
    return () => el.removeEventListener("wheel", handleWheel);
  }, [isOpen]);

  const handleSelect = (timezoneValue: string) => {
    onChange(timezoneValue);
    setIsOpen(false);
    setHighlightedIndex(-1);
    inputRef.current?.blur();
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setSearchQuery(newValue);
    setIsOpen(true);
    setHighlightedIndex(-1); // Reset highlight when typing

    // Only propagate changes when the user types an exact IANA timezone match.
    // Do NOT call onChange with partial search text — that would store an
    // invalid timezone in the parent's config state and cause a 400 when saving.
    // The value is committed via handleSelect when the user picks from the list.
    const exactMatch = ALL_TIMEZONES.find((tz) => tz.value.toLowerCase() === newValue.toLowerCase());
    if (exactMatch) {
      onChange(exactMatch.value);
    }
  };

  const updateDropdownPosition = () => {
    if (containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const dropdownMaxHeight = 240; // max-h-60 = 15rem = 240px
      const spaceBelow = window.innerHeight - rect.bottom;
      const top =
        spaceBelow >= dropdownMaxHeight || spaceBelow >= rect.top ? rect.bottom + 4 : rect.top - dropdownMaxHeight - 4;
      setDropdownStyle({
        position: "fixed",
        top,
        left: rect.left,
        width: rect.width,
        zIndex: 9999,
        pointerEvents: "auto",
      });
    }
  };

  const handleInputFocus = () => {
    updateDropdownPosition();
    setIsOpen(true);
  };

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") {
      setIsOpen(false);
      setHighlightedIndex(-1);
      inputRef.current?.blur();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      if (!isOpen && filteredTimezones.length > 0) {
        setIsOpen(true);
      }
      if (filteredTimezones.length > 0) {
        const maxIndex = Math.min(filteredTimezones.length - 1, 49); // Max 50 items shown
        setHighlightedIndex((prev) => {
          const newIndex = prev < maxIndex ? prev + 1 : 0;
          // Scroll highlighted item into view after state update
          setTimeout(() => {
            const highlightedElement = listRef.current?.children[newIndex] as HTMLElement;
            if (highlightedElement) {
              highlightedElement.scrollIntoView({ block: "nearest", behavior: "smooth" });
            }
          }, 0);
          return newIndex;
        });
      }
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      if (filteredTimezones.length > 0) {
        const maxIndex = Math.min(filteredTimezones.length - 1, 49);
        setHighlightedIndex((prev) => {
          const newIndex = prev > 0 ? prev - 1 : maxIndex;
          // Scroll highlighted item into view after state update
          setTimeout(() => {
            const highlightedElement = listRef.current?.children[newIndex] as HTMLElement;
            if (highlightedElement) {
              highlightedElement.scrollIntoView({ block: "nearest", behavior: "smooth" });
            }
          }, 0);
          return newIndex;
        });
      }
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (highlightedIndex >= 0 && highlightedIndex < filteredTimezones.length) {
        // Select highlighted item
        handleSelect(filteredTimezones[highlightedIndex].value);
      } else if (filteredTimezones.length > 0) {
        // Select first item if nothing highlighted
        handleSelect(filteredTimezones[0].value);
      }
    }
  };

  return (
    <div className={cn("relative", className)} ref={containerRef}>
      <div className="relative">
        <Input
          ref={inputRef}
          id={id}
          type="text"
          role="combobox"
          aria-expanded={isOpen}
          aria-autocomplete="list"
          aria-label={t("ariaLabel")}
          value={searchQuery}
          onChange={handleInputChange}
          onFocus={handleInputFocus}
          onKeyDown={handleInputKeyDown}
          disabled={disabled}
          placeholder={t("placeholder")}
          className={cn("pr-10", !isValid && value && "border-destructive focus-visible:ring-destructive")}
        />
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="absolute right-0 top-0 h-full px-2 py-1 hover:bg-transparent"
          onClick={() => {
            updateDropdownPosition();
            setIsOpen(!isOpen);
          }}
          disabled={disabled}
          tabIndex={-1}
          aria-label={t("toggleAriaLabel")}
        >
          <ChevronsUpDown className="h-4 w-4 text-muted-foreground" />
        </Button>
      </div>

      {typeof window !== "undefined" && isOpen && filteredTimezones.length > 0
        ? createPortal(
            <div
              ref={listRef}
              role="listbox"
              aria-label={t("optionsAriaLabel")}
              style={dropdownStyle}
              className="max-h-60 overflow-auto rounded-md border bg-popover text-popover-foreground shadow-md"
            >
              {filteredTimezones.slice(0, 50).map((timezone, index) => {
                const isHighlighted = index === highlightedIndex;
                const isSelected = value === timezone.value;
                return (
                  <button
                    key={timezone.value}
                    type="button"
                    aria-selected={isSelected}
                    className={cn(
                      "relative flex w-full cursor-pointer select-none items-center rounded-sm px-2 py-1.5 text-sm outline-none",
                      "hover:bg-accent hover:text-accent-foreground",
                      "focus:bg-accent focus:text-accent-foreground",
                      isHighlighted && "bg-accent text-accent-foreground",
                      isSelected && "bg-accent/50",
                    )}
                    onClick={() => handleSelect(timezone.value)}
                    onMouseEnter={() => setHighlightedIndex(index)}
                  >
                    {isSelected && <Check className="mr-2 h-4 w-4" />}
                    <span className={isSelected ? "" : "ml-6"}>{timezone.label}</span>
                  </button>
                );
              })}
              {filteredTimezones.length > 50 && (
                <div className="px-2 py-1.5 text-xs text-muted-foreground">
                  {t("showingFirst", { total: filteredTimezones.length })}
                </div>
              )}
            </div>,
            document.body,
          )
        : null}

      {!isValid && value && <p className="mt-1 text-xs text-destructive">{t("invalidTimezone")}</p>}
    </div>
  );
}
