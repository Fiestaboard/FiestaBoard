"use client";

import { Box, Text, type TimezoneOption, TimezonePicker as UITimezonePicker } from "@fiestaboard/ui";
import { useEffect, useMemo } from "react";

import { useTranslations } from "@/i18n/translations";
import { ALL_TIMEZONES } from "@/lib/timezone-utils";
import { cn } from "@/lib/utils";

/**
 * IANA timezone combobox from `@fiestaboard/ui`, wired to the app.
 *
 * The combobox itself — the filtering, the portalled listbox, the
 * `aria-activedescendant` keyboard model — lives in the package. What stays
 * here is what the package cannot know: the app's curated zone list, the
 * `timezonePicker` message namespace, and the invalid-value message.
 *
 * `ALL_TIMEZONES` already folds the offset into each label
 * (`"America/Los Angeles (UTC-8)"`), which is exactly what the app's rows and
 * its closed input have always shown. Passing that label through with an
 * empty `offset` keeps both reading as before instead of printing the offset
 * twice — once inside the label and once in the package's offset column.
 */
const ZONES: TimezoneOption[] = ALL_TIMEZONES.map((tz) => ({ id: tz.value, label: tz.label, offset: "" }));

/** What the old picker sliced its portalled list down to. */
const VISIBLE_MATCHES = 50;

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

  // Validity is a property of the STORED value, not of the text currently in
  // the box. The package's own `onValidityChange` reports the latter, which
  // would flag the field mid-word while someone types a zone name — so the
  // app keeps owning this check and leaves that callback unused.
  const isValid = useMemo(() => {
    if (!value) return true; // Empty is valid (will use default)
    return ALL_TIMEZONES.some((tz) => tz.value === value);
  }, [value]);

  useEffect(() => {
    onValidationChange?.(isValid);
  }, [isValid, onValidationChange]);

  return (
    <Box className={cn("relative", className)}>
      <UITimezonePicker
        id={id}
        value={value}
        onValueChange={onChange}
        timezones={ZONES}
        limit={VISIBLE_MATCHES}
        disabled={disabled}
        aria-label={t("ariaLabel")}
        labels={{ placeholder: t("placeholder"), list: t("optionsAriaLabel") }}
        className={cn(!isValid && value && "border-destructive")}
      />
      {!isValid && value && (
        <Text size="xs" tone="destructive" className="mt-1">
          {t("invalidTimezone")}
        </Text>
      )}
    </Box>
  );
}
