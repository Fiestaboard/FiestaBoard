"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Moon } from "lucide-react";
import { useTranslations } from "@/i18n/translations";
import { useDeferredValue, useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { TimePicker } from "@/components/ui/time-picker";
import { usePages } from "@/hooks/use-board";
import { api } from "@/lib/api";
import { localTimeToUTC, utcToLocalTime } from "@/lib/timezone-utils";

type SilenceMode = "indicator" | "freeze" | "page";

export function SilenceSchedule() {
  const t = useTranslations("generalSettings");
  const tc = useTranslations("common");
  const queryClient = useQueryClient();

  const [hasChanges, setHasChanges] = useState(false);
  const [silenceEnabled, setSilenceEnabled] = useState(false);
  const [silenceStartTime, setSilenceStartTime] = useState("20:00");
  const [silenceEndTime, setSilenceEndTime] = useState("07:00");
  const [silenceMode, setSilenceMode] = useState<SilenceMode>("indicator");
  const [silencePageId, setSilencePageId] = useState<string>("");
  const [silenceIndicatorText, setSilenceIndicatorText] = useState<string>("SNOOZING");
  const [silenceIndicatorPosition, setSilenceIndicatorPosition] = useState<string>("center");

  const { data: allSettings, isLoading } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  const generalConfig = allSettings?.general;
  const silenceConfig = allSettings?.silence_schedule;
  const deferredSilenceConfig = useDeferredValue(silenceConfig);
  const initializedRef = useRef(false);

  useEffect(() => {
    if (initializedRef.current) return;
    const rawConfig = (deferredSilenceConfig as { config?: Record<string, unknown> } | undefined)?.config;
    if (rawConfig && generalConfig?.timezone) {
      const userTimezone = generalConfig.timezone ?? "America/Los_Angeles";
      const config = rawConfig;

      setSilenceEnabled((config.enabled as boolean) ?? false);

      const startUtc = config.start_time as string;
      const endUtc = config.end_time as string;
      if (startUtc && endUtc) {
        setSilenceStartTime(utcToLocalTime(startUtc, userTimezone) || "20:00");
        setSilenceEndTime(utcToLocalTime(endUtc, userTimezone) || "07:00");
      }

      const rawMode = (config.mode as string) ?? "indicator";
      setSilenceMode(rawMode === "freeze" || rawMode === "page" ? rawMode : "indicator");
      setSilencePageId(((config.page_id as string) ?? "") || "");
      setSilenceIndicatorText(((config.indicator_text as string) ?? "") || "SNOOZING");
      setSilenceIndicatorPosition(((config.indicator_position as string) ?? "") || "center");

      setHasChanges(false);
      initializedRef.current = true;
    }
  }, [deferredSilenceConfig, generalConfig?.timezone]);

  const updateSilenceMutation = useMutation({
    mutationFn: (data: Parameters<typeof api.updateSilenceSchedule>[0]) => api.updateSilenceSchedule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["all-settings"], refetchType: "active" });
      queryClient.invalidateQueries({ queryKey: ["silence-status"], refetchType: "active" });
      toast.success(t("toastSettingsSaved"));
    },
    onError: (error: Error) => {
      toast.error(t("toastSilenceSaveFailed", { error: error.message }));
    },
  });

  const { data: pagesData } = usePages();
  const availablePages = pagesData?.pages ?? [];

  const isSaving = updateSilenceMutation.isPending;

  const handleSilenceToggle = (checked: boolean) => {
    setSilenceEnabled(checked);
    setHasChanges(true);
  };

  const handleSilenceTimeChange = (field: "start" | "end", value: string) => {
    if (field === "start") setSilenceStartTime(value);
    else setSilenceEndTime(value);
    setHasChanges(true);
  };

  const handleSilenceModeChange = (mode: SilenceMode) => {
    setSilenceMode(mode);
    setHasChanges(true);
  };

  const handleSilencePageChange = (pageId: string) => {
    setSilencePageId(pageId);
    setHasChanges(true);
  };

  const handleSilenceIndicatorTextChange = (text: string) => {
    setSilenceIndicatorText(text.toUpperCase());
    setHasChanges(true);
  };

  const handleSilenceIndicatorPositionChange = (position: string) => {
    setSilenceIndicatorPosition(position);
    setHasChanges(true);
  };

  const handleSave = async () => {
    const timezone = generalConfig?.timezone ?? "America/Los_Angeles";
    const startUtc = localTimeToUTC(silenceStartTime, timezone);
    const endUtc = localTimeToUTC(silenceEndTime, timezone);

    // "page" mode without a page selected: API would 400 — keep form state, skip save.
    if (silenceMode === "page" && !silencePageId) return;

    if (startUtc && endUtc) {
      await updateSilenceMutation.mutateAsync({
        enabled: silenceEnabled,
        start_time: startUtc,
        end_time: endUtc,
        mode: silenceMode,
        page_id: silencePageId || null,
        indicator_text: silenceIndicatorText || null,
        indicator_position: silenceIndicatorPosition || null,
      });
    }
    setHasChanges(false);
  };

  useEffect(() => {
    if (!hasChanges || updateSilenceMutation.isPending) return;
    const timeoutId = setTimeout(() => {
      handleSave();
    }, 1000);
    return () => clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    silenceEnabled,
    silenceStartTime,
    silenceEndTime,
    silenceMode,
    silencePageId,
    silenceIndicatorText,
    silenceIndicatorPosition,
    hasChanges,
  ]);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Moon className="h-4 w-4" />
          {t("silenceScheduleLabel")}
        </CardTitle>
        <CardDescription>{t("silenceScheduleDescription")}</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-5 w-11 rounded-full" />
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-48" />
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between gap-3">
              <label htmlFor="silence-enabled" className="text-sm font-medium cursor-pointer">
                {t("silenceScheduleLabel")}
              </label>
              <Switch
                checked={silenceEnabled}
                onCheckedChange={handleSilenceToggle}
                disabled={isSaving}
                id="silence-enabled"
              />
            </div>

            {silenceEnabled && (
              <div className="mt-6 space-y-6">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="silence-start" className="text-sm font-medium">
                      {t("startTimeLabel")}
                    </Label>
                    <TimePicker
                      id="silence-start"
                      value={silenceStartTime}
                      onChange={(val) => handleSilenceTimeChange("start", val)}
                      disabled={isSaving}
                    />
                    <p className="text-xs text-muted-foreground">{t("whenSilenceBegins")}</p>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="silence-end" className="text-sm font-medium">
                      {t("endTimeLabel")}
                    </Label>
                    <TimePicker
                      id="silence-end"
                      value={silenceEndTime}
                      onChange={(val) => handleSilenceTimeChange("end", val)}
                      disabled={isSaving}
                    />
                    <p className="text-xs text-muted-foreground">{t("whenSilenceEnds")}</p>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="silence-mode" className="text-sm font-medium">
                    {t("silenceModeLabel")}
                  </Label>
                  <Select
                    value={silenceMode}
                    onValueChange={(val) => handleSilenceModeChange(val as SilenceMode)}
                    disabled={isSaving}
                  >
                    <SelectTrigger id="silence-mode" className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="indicator">{t("silenceModeIndicator")}</SelectItem>
                      <SelectItem value="freeze">{t("silenceModeFreeze")}</SelectItem>
                      <SelectItem value="page">{t("silenceModePage")}</SelectItem>
                    </SelectContent>
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    {silenceMode === "indicator" && t("silenceModeIndicatorHelp")}
                    {silenceMode === "freeze" && t("silenceModeFreezeHelp")}
                    {silenceMode === "page" && t("silenceModePageHelp")}
                  </p>
                </div>

                {silenceMode === "indicator" && (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="silence-indicator-text" className="text-sm font-medium">
                        {t("silenceIndicatorTextLabel")}
                      </Label>
                      <Input
                        id="silence-indicator-text"
                        value={silenceIndicatorText}
                        onChange={(e) => handleSilenceIndicatorTextChange(e.target.value)}
                        disabled={isSaving}
                        maxLength={22}
                        placeholder="SNOOZING"
                        className="uppercase"
                      />
                      <p className="text-xs text-muted-foreground">{t("silenceIndicatorTextHelp")}</p>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="silence-indicator-position" className="text-sm font-medium">
                        {t("silenceIndicatorPositionLabel")}
                      </Label>
                      <Select
                        value={silenceIndicatorPosition}
                        onValueChange={handleSilenceIndicatorPositionChange}
                        disabled={isSaving}
                      >
                        <SelectTrigger id="silence-indicator-position" className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="top-left">{t("positionTopLeft")}</SelectItem>
                          <SelectItem value="top-right">{t("positionTopRight")}</SelectItem>
                          <SelectItem value="center">{t("positionCenter")}</SelectItem>
                          <SelectItem value="bottom-left">{t("positionBottomLeft")}</SelectItem>
                          <SelectItem value="bottom-right">{t("positionBottomRight")}</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </>
                )}

                {silenceMode === "page" && (
                  <div className="space-y-2">
                    <Label htmlFor="silence-page" className="text-sm font-medium">
                      {t("silencePageLabel")}
                    </Label>
                    <Select
                      value={silencePageId || undefined}
                      onValueChange={handleSilencePageChange}
                      disabled={isSaving || availablePages.length === 0}
                    >
                      <SelectTrigger id="silence-page" className="w-full">
                        <SelectValue placeholder={t("silencePagePlaceholder")} />
                      </SelectTrigger>
                      <SelectContent>
                        {availablePages.map((p) => (
                          <SelectItem key={p.id} value={p.id}>
                            {p.name || p.id}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground">{t("silencePageHelp")}</p>
                  </div>
                )}
              </div>
            )}

            {isSaving && (
              <div className="flex items-center justify-center gap-2 pt-4 mt-4 border-t text-xs text-muted-foreground">
                <div className="h-3 w-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                <span>{tc("savingIndicator")}</span>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
