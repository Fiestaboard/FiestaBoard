"use client";

import {
  BoardDisplay as UIBoardDisplay,
  type BoardDisplayProps as UIBoardDisplayProps,
  type FlapSpeed,
} from "@fiestaboard/ui";
import { memo, useCallback } from "react";

import { useBoardAnimationsEnabled, useBoardFlapSpeed } from "@/hooks/use-board-animations";
import { useTranslations } from "@/i18n/translations";

/**
 * The split-flap board, from `@fiestaboard/ui`.
 *
 * This file used to be a ~1,400-line fork of that component. The fork existed
 * because the app needed four things the package deliberately does not know
 * about — the user's animation kill switch, the user's flap-speed setting, and
 * the app's translated accessible names — and the package had no props for
 * them. It does now, so what is left here is only that wiring.
 *
 * Keeping the fork meant every upstream board fix had to be ported by hand,
 * and the two had already diverged on six of them (FiestaUI #176–#180, #196).
 * Two were ported in #1555; the rest arrive with this file.
 */

/**
 * Everything the package's board takes, minus what this wrapper supplies.
 *
 * `animationsEnabled` and the three label props are omitted on purpose: a
 * caller passing its own would be quietly opting out of the user's animation
 * settings or shipping an untranslated string. Both are decisions this
 * component exists to make once.
 */
export type BoardDisplayProps = Omit<
  UIBoardDisplayProps,
  "animationsEnabled" | "loadingLabel" | "emptyLabel" | "messageLabel"
>;

/**
 * The props every app-rendered board shares: the animation gate, the user's
 * cadence, and translated accessible names.
 *
 * Shared with {@link ScaledBoardDisplay} so a scaled board and an unscaled one
 * cannot end up wired differently — the scaled wrapper is the one most surfaces
 * actually render, and it would be the one to drift.
 *
 * @param flapSpeed An explicit override for the user's setting. Only the
 *   settings live preview passes it, so a user can compare cadences before
 *   committing to one.
 */
export function useBoardChrome(flapSpeed?: FlapSpeed) {
  const t = useTranslations("boardDisplay");
  const animationsEnabled = useBoardAnimationsEnabled();
  const settingFlapSpeed = useBoardFlapSpeed();

  // Stable identity matters here: the package's `BoardDisplay` compares
  // `messageLabel` by reference in its memo comparator, so an inline arrow
  // would defeat memoization of a ~132-tile grid on every parent render. `t`
  // is itself memoized on [language, namespace], so this survives re-renders
  // and still recomputes on a language switch.
  const messageLabel = useCallback((message: string) => t("withMessage", { message }), [t]);

  return {
    // `useBoardAnimationsEnabled` collapses `board_animations`, `reduce_motion`
    // and `prefers-reduced-motion: reduce` into one boolean. The package ANDs
    // its own reduced-motion check on top, so a `reduce` user cannot get a
    // cascade by picking a slower preset — see FiestaUI #180.
    animationsEnabled,
    // Omit the prop and the board follows the user's `board_flap_speed`
    // setting, exactly as animations follow `board_animations`.
    flapSpeed: flapSpeed ?? settingFlapSpeed,
    loadingLabel: t("loading"),
    emptyLabel: t("empty"),
    messageLabel,
  };
}

export const BoardDisplay = memo(function BoardDisplay({ flapSpeed, ...props }: BoardDisplayProps) {
  const chrome = useBoardChrome(flapSpeed);
  return <UIBoardDisplay {...props} {...chrome} />;
});
