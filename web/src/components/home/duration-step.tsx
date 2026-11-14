"use client";

import { buildDurationOptions, DurationChipGroup, Stack, Text } from "@fiestaboard/ui";
import { useId, useMemo } from "react";

import { useLocale, useTranslations } from "@/i18n/translations";

import { type DurationChoice, formatClock, formatSpan, holdEndsAt, type ScheduleNextChange } from "./home-status";

export interface DurationStepProps {
  /** The page being held ("Taco Tuesday"); the question falls back to "it". */
  name?: string;
  value: DurationChoice;
  onValueChange: (value: DurationChoice) => void;
  /** H2's next Schedule change on the target display, or null (no chip for it). */
  nextChange: ScheduleNextChange | null;
  /** The page the Schedule resumes with after `nextChange`, when known. */
  nextPageName?: string | null;
  /** The target display is in Schedule Mode. */
  scheduleEnabled: boolean;
  /** Manual Mode: the page that comes back after a timed hold. */
  manualPageName?: string | null;
  /**
   * Manual Mode Change Page: "Until I cancel" pins the page as the new manual
   * page instead of holding an Override (Jev, p = 0.81; see the 2.2 plan).
   */
  untilCancelPins?: boolean;
  /** The Override running on the display now; a new hold replaces it. */
  replacesName?: string | null;
  /** `grid` in a narrow sheet; `auto` elsewhere. */
  layout?: "auto" | "grid" | "row";
  /** The clock the outcome is computed against. */
  now: Date;
}

/**
 * The ONE duration step both verbs end in (CANON "Two verbs only"): the 07a
 * question, FiestaUI's DurationChipGroup (15 min · 1 hr · Until <next
 * change> · Until I cancel) and the outcome sentence under it.
 */
export function DurationStep({
  name,
  value,
  onValueChange,
  nextChange,
  nextPageName = null,
  scheduleEnabled,
  manualPageName = null,
  untilCancelPins = false,
  replacesName = null,
  layout = "auto",
  now,
}: DurationStepProps) {
  const t = useTranslations("home.duration");
  const locale = useLocale();
  const questionId = useId();

  const options = useMemo(
    () =>
      buildDurationOptions({
        nextChange: nextChange ? t("untilTime", { time: formatClock(nextChange.at, locale) }) : undefined,
        labels: { fifteenMinutes: t("fifteenMinutes"), oneHour: t("oneHour"), untilCancel: t("untilCancel") },
      }),
    [nextChange, t, locale],
  );

  const outcome = useMemo(() => {
    const ends = holdEndsAt(value, nextChange, now);
    let sentence: string;
    if (!ends) {
      sentence = untilCancelPins && !scheduleEnabled ? t("outcomePin") : t("outcomeUntilCancel");
    } else {
      const time = formatClock(ends, locale);
      const span = formatSpan(ends.getTime() - now.getTime());
      if (scheduleEnabled) {
        sentence =
          value === "next-change" && nextPageName
            ? t("outcomeScheduleNext", { time, span, page: nextPageName })
            : t("outcomeSchedule", { time, span });
      } else {
        sentence = manualPageName
          ? t("outcomeManual", { time, span, page: manualPageName })
          : t("outcomeManualNoPage", { time, span });
      }
    }
    // A pin replaces a running Override too: Change Page clears it first.
    return replacesName ? `${sentence} ${t("replaces", { name: replacesName })}` : sentence;
  }, [value, nextChange, now, untilCancelPins, scheduleEnabled, nextPageName, manualPageName, replacesName, t, locale]);

  return (
    <Stack gap="3">
      <Text id={questionId} size="sm" weight="semibold">
        {name ? t("questionNamed", { name }) : t("question")}
      </Text>
      <DurationChipGroup
        aria-labelledby={questionId}
        options={options}
        value={value}
        onValueChange={(next) => onValueChange(next as DurationChoice)}
        layout={layout}
        outcome={outcome}
      />
    </Stack>
  );
}

/** 07a preselects the next change; otherwise 1 hr in Schedule Mode, Until I cancel in Manual Mode. */
export function defaultDurationChoice(
  nextChange: ScheduleNextChange | null,
  { scheduleEnabled }: { scheduleEnabled: boolean },
): DurationChoice {
  if (nextChange) return "next-change";
  return scheduleEnabled ? "1h" : "until-cancel";
}
