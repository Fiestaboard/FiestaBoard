"use client";

import {
  Box,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  FLAP_SPEED_PRESETS,
  type FlapSpeedPreset,
  Flex,
  Label,
  Skeleton,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Info, Sparkles } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { BoardDisplay } from "@/components/board-display";
import { useBoardAnimationsEnabled } from "@/hooks/use-board-animations";
import { useTranslations } from "@/i18n/translations";
import { api, type BoardAnimationsMode, type DisplaySettings, type SiteAnimationsMode } from "@/lib/api";

const BOARD_OPTIONS: BoardAnimationsMode[] = ["on", "desktop", "off"];
const SITE_OPTIONS: SiteAnimationsMode[] = ["on", "off"];

// Slowest first would bury `standard`; this is the order the presets read in
// as a spectrum, with the shipped default in the middle.
const FLAP_SPEED_OPTIONS: FlapSpeedPreset[] = ["hardware", "quick", "standard", "relaxed"];

// Two Note-sized (15x3) messages the preview alternates between. Every tile
// changes, so the cascade is visible rather than a couple of stray flips.
const PREVIEW_MESSAGES = ["\n  FLIP  SPEED\n", "\n  WATCH  ME\n"];
const PREVIEW_INTERVAL_MS = 3200;

/**
 * A live board that keeps changing its message so the chosen cadence can be
 * judged before it is saved — the difference between `quick` and `standard`
 * is not something a label conveys.
 *
 * It re-keys on `speed` so switching presets restarts the cycle immediately
 * instead of making the user wait out the current dwell.
 */
function FlapSpeedPreview({ speed, enabled }: { speed: FlapSpeedPreset; enabled: boolean }) {
  const [index, setIndex] = useState(0);
  const speedRef = useRef(speed);

  useEffect(() => {
    if (!enabled) return;
    // A preset change restarts the cycle with an immediate flip, so the new
    // cadence is on screen straight away.
    if (speedRef.current !== speed) {
      speedRef.current = speed;
      setIndex((i) => i + 1);
    }
    const id = setInterval(() => setIndex((i) => i + 1), PREVIEW_INTERVAL_MS);
    return () => clearInterval(id);
  }, [speed, enabled]);

  return (
    <BoardDisplay
      message={PREVIEW_MESSAGES[index % PREVIEW_MESSAGES.length]}
      deviceType="note"
      size="sm"
      flapSpeed={speed}
    />
  );
}

const BOARD_LABEL_KEY: Record<BoardAnimationsMode, string> = {
  on: "boardAnimationsOn",
  desktop: "boardAnimationsDesktop",
  off: "boardAnimationsOff",
};

const BOARD_HINT_KEY: Record<BoardAnimationsMode, string> = {
  on: "boardAnimationsOnHint",
  desktop: "boardAnimationsDesktopHint",
  off: "boardAnimationsOffHint",
};

const SITE_LABEL_KEY: Record<SiteAnimationsMode, string> = {
  on: "siteAnimationsOn",
  off: "siteAnimationsOff",
};

export function AnimationSettings() {
  const t = useTranslations("profile");
  const queryClient = useQueryClient();

  const { data: allSettings, isLoading } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  const [boardMode, setBoardMode] = useState<BoardAnimationsMode>("on");
  const [siteMode, setSiteMode] = useState<SiteAnimationsMode>("on");
  const [flapSpeed, setFlapSpeed] = useState<FlapSpeedPreset>("standard");

  useEffect(() => {
    const display = allSettings?.display;
    if (display) {
      setBoardMode(display.board_animations ?? "on");
      setSiteMode(display.site_animations ?? "on");
      const stored = display.board_flap_speed;
      // A raw millisecond count (the API's escape hatch) has no radio to
      // select; leave the group showing the default rather than inventing one.
      if (typeof stored === "string" && stored in FLAP_SPEED_PRESETS) {
        setFlapSpeed(stored as FlapSpeedPreset);
      }
    }
  }, [allSettings?.display]);

  const updateMutation = useMutation({
    mutationFn: (settings: Partial<DisplaySettings>) => api.updateDisplaySettings(settings),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["all-settings"] }),
    onError: (error: Error) => toast.error(error.message),
  });

  const reduceMotion = allSettings?.display?.reduce_motion ?? false;

  const handleBoardChange = (mode: BoardAnimationsMode) => {
    setBoardMode(mode);
    updateMutation.mutate({ board_animations: mode });
  };

  const handleSiteChange = (mode: SiteAnimationsMode) => {
    setSiteMode(mode);
    updateMutation.mutate({ site_animations: mode });
  };

  const handleFlapSpeedChange = (preset: FlapSpeedPreset) => {
    setFlapSpeed(preset);
    updateMutation.mutate({ board_flap_speed: preset });
  };

  // The cadence only means anything while the board actually flips. Mirror the
  // same gate the board itself uses (`board_animations`, `reduce_motion`, and
  // `prefers-reduced-motion`) rather than re-deriving a second, divergent one:
  // a user who asked for reduced motion must not get a cascade because they
  // picked "relaxed".
  const boardAnimating = useBoardAnimationsEnabled();

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4" />
          {t("animationsTitle")}
        </CardTitle>
        <CardDescription>{t("animationsDescription")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {isLoading ? (
          <Skeleton className="h-20 w-full" />
        ) : (
          <>
            <Stack gap="2">
              <Box>
                <Label className="text-sm font-medium">{t("boardAnimationsLabel")}</Label>
                <Text size="xs" tone="muted" className="mt-0.5">
                  {t("boardAnimationsHint")}
                </Text>
              </Box>
              <Flex wrap gap="2" role="radiogroup" aria-label={t("boardAnimationsLabel")}>
                {BOARD_OPTIONS.map((option) => {
                  const selected = boardMode === option;
                  return (
                    <button
                      key={option}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => handleBoardChange(option)}
                      disabled={updateMutation.isPending}
                      className={`px-3 py-1.5 rounded-md border text-xs font-medium transition-colors ${
                        selected
                          ? "border-brand bg-brand/10 text-brand"
                          : "border-muted hover:border-brand/50 text-foreground"
                      }`}
                    >
                      {t(BOARD_LABEL_KEY[option])}
                    </button>
                  );
                })}
              </Flex>
              <Text size="xs" tone="muted">
                {t(BOARD_HINT_KEY[boardMode])}
              </Text>
            </Stack>

            <Stack gap="2" className="pt-2 border-t">
              <Box>
                <Label className="text-sm font-medium">{t("flapSpeedLabel")}</Label>
                <Text size="xs" tone="muted" className="mt-0.5">
                  {t("flapSpeedHint")}
                </Text>
              </Box>
              <Flex wrap gap="2" role="radiogroup" aria-label={t("flapSpeedLabel")}>
                {FLAP_SPEED_OPTIONS.map((option) => {
                  const selected = flapSpeed === option;
                  return (
                    <button
                      key={option}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => handleFlapSpeedChange(option)}
                      disabled={updateMutation.isPending}
                      className={`px-3 py-1.5 rounded-md border text-xs font-medium transition-colors ${
                        selected
                          ? "border-brand bg-brand/10 text-brand"
                          : "border-muted hover:border-brand/50 text-foreground"
                      }`}
                    >
                      {t(`flapSpeed_${option}`)}
                    </button>
                  );
                })}
              </Flex>
              <Text size="xs" tone="muted">
                {t(`flapSpeed_${flapSpeed}Hint`, { ms: FLAP_SPEED_PRESETS[flapSpeed] })}
              </Text>

              {/* Users have a second, unrelated speed control under
                  Behavior → Board Transitions (step_interval_ms, sent to the
                  physical unit over the Local API). Without this the two read
                  as the same setting configured twice. */}
              <Flex align="start" gap="2" className="p-2.5 rounded-md bg-muted/50">
                <Info className="h-3.5 w-3.5 mt-0.5 shrink-0 text-muted-foreground" />
                <Text as="span" size="xs" tone="muted">
                  {t("flapSpeedScreenOnlyNote")}
                </Text>
              </Flex>

              {boardAnimating ? (
                <Stack gap="1.5" className="pt-1">
                  <Text size="xs" tone="muted">
                    {t("flapSpeedPreviewLabel")}
                  </Text>
                  <Box className="flex justify-center">
                    <FlapSpeedPreview speed={flapSpeed} enabled={boardAnimating} />
                  </Box>
                </Stack>
              ) : (
                <Text size="xs" tone="muted" className="italic">
                  {t("flapSpeedInactive")}
                </Text>
              )}
            </Stack>

            <Stack gap="2" className="pt-2 border-t">
              <Box>
                <Label className="text-sm font-medium">{t("siteAnimationsLabel")}</Label>
                <Text size="xs" tone="muted" className="mt-0.5">
                  {t("siteAnimationsHint")}
                </Text>
              </Box>
              <Flex wrap gap="2" role="radiogroup" aria-label={t("siteAnimationsLabel")}>
                {SITE_OPTIONS.map((option) => {
                  const selected = siteMode === option;
                  return (
                    <button
                      key={option}
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => handleSiteChange(option)}
                      disabled={updateMutation.isPending}
                      className={`px-3 py-1.5 rounded-md border text-xs font-medium transition-colors ${
                        selected
                          ? "border-brand bg-brand/10 text-brand"
                          : "border-muted hover:border-brand/50 text-foreground"
                      }`}
                    >
                      {t(SITE_LABEL_KEY[option])}
                    </button>
                  );
                })}
              </Flex>
            </Stack>

            {reduceMotion && (
              <Text size="xs" tone="muted" className="italic">
                {t("animationsReduceMotionOverride")}
              </Text>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
