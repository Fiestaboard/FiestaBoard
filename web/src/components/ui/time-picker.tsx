"use client";

import { TimePicker as UITimePicker } from "@fiestaboard/ui";

import { useTranslations } from "@/i18n/translations";

/**
 * Time-of-day picker from `@fiestaboard/ui`, wired to the app's catalog.
 *
 * The picker itself — the trigger, the hour/minute listboxes, the preset
 * chips, the popover and its keyboard model — lives in the package. All this
 * file still owns is the `timePicker` message namespace, which the package
 * cannot resolve for itself, and the `onChange` prop name the app's call sites
 * already use.
 */
interface TimePickerProps {
  value: string; // HH:MM format
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
  id?: string;
  "aria-label"?: string;
}

export function TimePicker({ value, onChange, placeholder = "00:00", ...props }: TimePickerProps) {
  const t = useTranslations("timePicker");

  return (
    <UITimePicker
      {...props}
      value={value}
      onValueChange={onChange}
      placeholder={placeholder}
      labels={{ hour: t("hour"), minute: t("minute"), quickPresets: t("quickPresets") }}
    />
  );
}
