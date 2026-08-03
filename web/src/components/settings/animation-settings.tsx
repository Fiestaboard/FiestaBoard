"use client";

import { Box, Card, CardContent, CardDescription, CardHeader, CardTitle, Flex, Label, Skeleton, Stack, Text } from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import { api, type BoardAnimationsMode, type DisplaySettings, type SiteAnimationsMode } from "@/lib/api";

const BOARD_OPTIONS: BoardAnimationsMode[] = ["on", "desktop", "off"];
const SITE_OPTIONS: SiteAnimationsMode[] = ["on", "off"];

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

  useEffect(() => {
    const display = allSettings?.display;
    if (display) {
      setBoardMode(display.board_animations ?? "on");
      setSiteMode(display.site_animations ?? "on");
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
