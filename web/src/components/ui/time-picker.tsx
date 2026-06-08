"use client";

import { Clock } from "lucide-react";
import { useTranslations } from "@/i18n/translations";
import type { CSSProperties } from "react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface TimePickerProps {
  value: string; // HH:MM format
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
}

export function TimePicker({
  value,
  onChange,
  placeholder = "00:00",
  className,
  disabled,
  id,
  "aria-label": ariaLabel,
}: TimePickerProps) {
  const t = useTranslations("timePicker");
  const [isOpen, setIsOpen] = useState(false);
  const [hours, setHours] = useState("00");
  const [minutes, setMinutes] = useState("00");
  const [dropdownStyle, setDropdownStyle] = useState<CSSProperties>({});
  const containerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Parse value on mount and when value changes
  useEffect(() => {
    if (value) {
      const [h, m] = value.split(":");
      if (h && m) {
        setHours(h.padStart(2, "0"));
        setMinutes(m.padStart(2, "0"));
      }
    } else {
      setHours("00");
      setMinutes("00");
    }
  }, [value]);

  // Close on outside click
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      const target = event.target as Node;
      const inContainer = containerRef.current?.contains(target);
      const inDropdown = dropdownRef.current?.contains(target);
      if (!inContainer && !inDropdown) {
        setIsOpen(false);
      }
    }

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [isOpen]);

  const handleHourChange = (newHour: string) => {
    setHours(newHour);
    onChange(`${newHour}:${minutes}`);
  };

  const handleMinuteChange = (newMinute: string) => {
    setMinutes(newMinute);
    onChange(`${hours}:${newMinute}`);
  };

  const formatDisplayValue = () => {
    if (!value) return "";
    const [h, m] = value.split(":");
    if (!h || !m) return "";
    const hour = parseInt(h, 10);
    const period = hour >= 12 ? "PM" : "AM";
    const displayHour = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
    return `${displayHour}:${m} ${period}`;
  };

  // Generate hour options (00-23)
  const hourOptions = Array.from({ length: 24 }, (_, i) => {
    const hour = i.toString().padStart(2, "0");
    const displayHour = i === 0 ? 12 : i > 12 ? i - 12 : i;
    const period = i >= 12 ? "PM" : "AM";
    return { value: hour, label: `${displayHour} ${period}`, hour24: i };
  });

  // Generate minute options (00-59, every 5 minutes)
  const minuteOptions = Array.from({ length: 12 }, (_, i) => {
    const minute = (i * 5).toString().padStart(2, "0");
    return { value: minute, label: minute };
  });

  const toggleDropdown = () => {
    if (disabled) return;
    if (!isOpen && containerRef.current) {
      const rect = containerRef.current.getBoundingClientRect();
      const dropdownHeight = 320; // approximate max height of the dropdown
      const spaceBelow = window.innerHeight - rect.bottom;
      const top =
        spaceBelow >= dropdownHeight || spaceBelow >= rect.top ? rect.bottom + 4 : rect.top - dropdownHeight - 4;
      setDropdownStyle({
        position: "fixed",
        top,
        left: rect.left,
        width: 256,
        zIndex: 9999,
      });
    }
    setIsOpen((prev) => !prev);
  };

  const dropdown = isOpen ? (
    <div ref={dropdownRef} style={dropdownStyle} className="rounded-md border bg-background p-4 shadow-md">
      <div className="flex gap-4">
        {/* Hours */}
        <div className="flex-1">
          <label className="text-xs font-medium text-muted-foreground mb-2 block">{t("hour")}</label>
          <div className="max-h-48 overflow-y-auto rounded-md border bg-background">
            {hourOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => handleHourChange(option.value)}
                className={cn(
                  "w-full px-3 py-2 text-sm text-left hover:bg-accent hover:text-accent-foreground transition-colors",
                  hours === option.value && "bg-accent text-accent-foreground font-medium",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>

        {/* Minutes */}
        <div className="flex-1">
          <label className="text-xs font-medium text-muted-foreground mb-2 block">{t("minute")}</label>
          <div className="max-h-48 overflow-y-auto rounded-md border bg-background">
            {minuteOptions.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => handleMinuteChange(option.value)}
                className={cn(
                  "w-full px-3 py-2 text-sm text-left hover:bg-accent hover:text-accent-foreground transition-colors",
                  minutes === option.value && "bg-accent text-accent-foreground font-medium",
                )}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Quick presets */}
      <div className="mt-4 pt-4 border-t">
        <div className="text-xs font-medium text-muted-foreground mb-2">{t("quickPresets")}</div>
        <div className="flex gap-2 flex-wrap">
          {[
            { label: "8 AM", value: "08:00" },
            { label: "12 PM", value: "12:00" },
            { label: "6 PM", value: "18:00" },
            { label: "8 PM", value: "20:00" },
            { label: "12 AM", value: "00:00" },
          ].map((preset) => (
            <button
              key={preset.value}
              type="button"
              onClick={() => {
                const [h, m] = preset.value.split(":");
                setHours(h);
                setMinutes(m);
                onChange(preset.value);
              }}
              className="px-2 py-1 text-xs rounded-md border hover:bg-accent transition-colors"
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  ) : null;

  return (
    <div ref={containerRef} className={cn("relative", className)}>
      <Button
        id={id}
        type="button"
        variant="outline"
        onClick={toggleDropdown}
        disabled={disabled}
        aria-label={ariaLabel}
        aria-expanded={isOpen}
        aria-haspopup="listbox"
        className={cn("w-full h-9 px-3 text-sm justify-start font-normal", !value && "text-muted-foreground")}
      >
        <Clock className="mr-2 h-4 w-4" />
        <span>{value ? formatDisplayValue() : placeholder}</span>
      </Button>

      {typeof window !== "undefined" && dropdown ? createPortal(dropdown, document.body) : null}
    </div>
  );
}
