"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
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
            <div className="space-y-2">
              <div>
                <Label className="text-sm font-medium">{t("boardAnimationsLabel")}</Label>
                <p className="text-xs text-muted-foreground mt-0.5">{t("boardAnimationsHint")}</p>
              </div>
              <div role="radiogroup" aria-label={t("boardAnimationsLabel")} className="flex flex-wrap gap-2">
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
              </div>
              <p className="text-xs text-muted-foreground">{t(BOARD_HINT_KEY[boardMode])}</p>
            </div>

            <div className="space-y-2 pt-2 border-t">
              <div>
                <Label className="text-sm font-medium">{t("siteAnimationsLabel")}</Label>
                <p className="text-xs text-muted-foreground mt-0.5">{t("siteAnimationsHint")}</p>
              </div>
              <div role="radiogroup" aria-label={t("siteAnimationsLabel")} className="flex flex-wrap gap-2">
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
              </div>
            </div>

            {reduceMotion && (
              <p className="text-xs text-muted-foreground italic">{t("animationsReduceMotionOverride")}</p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
