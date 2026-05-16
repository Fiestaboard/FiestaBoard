"use client";

import { useState, useEffect, useDeferredValue } from "react";
import { useTranslations } from "next-intl";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { TimePicker } from "@/components/ui/time-picker";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { toast } from "sonner";
import { CalendarClock } from "lucide-react";
import { api } from "@/lib/api";
import { usePages } from "@/hooks/use-board";
import { utcToLocalTime, localTimeToUTC } from "@/lib/timezone-utils";

type SilenceMode = "indicator" | "freeze" | "page";

export function GeneralSettings() {
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
  const [pollingInterval, setPollingInterval] = useState(15);
  const [boardReadIntervalLocal, setBoardReadIntervalLocal] = useState(30);
  const [boardReadIntervalCloud, setBoardReadIntervalCloud] = useState(180);

  // Fetch all settings in one request
  const { data: allSettings, isLoading: isLoadingSettings } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  // Extract individual settings from consolidated response
  const generalConfig = allSettings?.general;
  const silenceConfig = allSettings?.silence_schedule;
  const pollingSettings = allSettings?.polling;

  // Use deferred values for non-critical data to reduce re-render priority
  const deferredSilenceConfig = useDeferredValue(silenceConfig);
  const deferredPollingSettings = useDeferredValue(pollingSettings);

  const isLoadingSilence = isLoadingSettings;
  const isLoadingPolling = isLoadingSettings;


  // Initialize silence schedule when config loads
  useEffect(() => {
    if (deferredSilenceConfig?.config && generalConfig?.timezone) {
      const userTimezone = generalConfig.timezone ?? "America/Los_Angeles";
      const config = deferredSilenceConfig.config;

      setSilenceEnabled((config.enabled as boolean) ?? false);

      // Convert UTC times to local for display
      const startUtc = config.start_time as string;
      const endUtc = config.end_time as string;

      if (startUtc && endUtc) {
        const startLocal = utcToLocalTime(startUtc, userTimezone) || "20:00";
        const endLocal = utcToLocalTime(endUtc, userTimezone) || "07:00";
        setSilenceStartTime(startLocal);
        setSilenceEndTime(endLocal);
      }

      const rawMode = (config.mode as string) ?? "indicator";
      setSilenceMode(
        rawMode === "freeze" || rawMode === "page" ? rawMode : "indicator"
      );
      setSilencePageId(((config.page_id as string) ?? "") || "");
      setSilenceIndicatorText(((config.indicator_text as string) ?? "") || "SNOOZING");
      setSilenceIndicatorPosition(((config.indicator_position as string) ?? "") || "center");

      setHasChanges(false);
    }
  }, [deferredSilenceConfig, generalConfig?.timezone]);

  // Initialize polling interval when settings load
  useEffect(() => {
    if (deferredPollingSettings) {
      setPollingInterval(deferredPollingSettings.interval_seconds);
      setBoardReadIntervalLocal(deferredPollingSettings.board_read_interval_local ?? 30);
      setBoardReadIntervalCloud(deferredPollingSettings.board_read_interval_cloud ?? 180);
    }
  }, [deferredPollingSettings]);

  // Update silence schedule mutation (system feature endpoint, not plugin API)
  const updateSilenceMutation = useMutation({
    mutationFn: (data: {
      enabled: boolean;
      start_time: string;
      end_time: string;
      mode: SilenceMode;
      page_id: string | null;
    }) => api.updateSilenceSchedule(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["all-settings"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["silence-status"], refetchType: 'active' });
      toast.success(t("toastSettingsSaved"));
    },
    onError: (error: Error) => {
      toast.error(t("toastSilenceSaveFailed", { error: error.message }));
    },
  });

  // Update polling settings mutation
  const updatePollingMutation = useMutation({
    mutationFn: (updates: Parameters<typeof api.updatePollingSettings>[0]) =>
      api.updatePollingSettings(updates),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["polling-settings"] });
      if (data.requires_restart) {
        toast.success(t("toastPollingUpdatedRestart"), {
          duration: 5000,
        });
      } else {
        toast.success(t("toastPollingUpdated"));
      }
      setHasChanges(false);
    },
    onError: (error: Error) => {
      toast.error(t("toastPollingFailed", { error: error.message }));
    },
  });

  // Update board read interval mutation (separate so it doesn't trigger restart toast)
  const updateBoardReadIntervalMutation = useMutation({
    mutationFn: (updates: Parameters<typeof api.updatePollingSettings>[0]) =>
      api.updatePollingSettings(updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["polling-settings"] });
      toast.success(t("toastBoardReadIntervalUpdated"));
    },
    onError: (error: Error) => {
      toast.error(t("toastBoardReadIntervalFailed", { error: error.message }));
    },
  });

  const handlePollingIntervalChange = (value: string) => {
    const interval = parseInt(value, 10);
    if (!isNaN(interval) && interval >= 10) {
      setPollingInterval(interval);
      setHasChanges(true);
    }
  };

  const handlePollingIntervalBlur = () => {
    updatePollingMutation.mutate({ interval_seconds: pollingInterval });
  };

  const handleBoardReadIntervalLocalBlur = () => {
    const clamped = Math.max(20, boardReadIntervalLocal);
    setBoardReadIntervalLocal(clamped);
    updateBoardReadIntervalMutation.mutate({ board_read_interval_local: clamped });
  };

  const handleBoardReadIntervalCloudBlur = () => {
    const clamped = Math.max(20, boardReadIntervalCloud);
    setBoardReadIntervalCloud(clamped);
    updateBoardReadIntervalMutation.mutate({ board_read_interval_cloud: clamped });
  };

  const handleSilenceToggle = (checked: boolean) => {
    setSilenceEnabled(checked);
    setHasChanges(true);
  };

  const handleSilenceTimeChange = (field: "start" | "end", value: string) => {
    if (field === "start") {
      setSilenceStartTime(value);
    } else {
      setSilenceEndTime(value);
    }
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

  // Pages for the "page" mode selector. Only fetched while silence is
  // enabled; the underlying query is otherwise idle and shared with the
  // rest of the app.
  const { data: pagesData } = usePages();
  const availablePages = pagesData?.pages ?? [];

  const handleSave = async () => {
    const timezone = generalConfig?.timezone ?? "America/Los_Angeles";
    const startUtc = localTimeToUTC(silenceStartTime, timezone);
    const endUtc = localTimeToUTC(silenceEndTime, timezone);

    // If "page" mode is chosen but no page is selected, don't auto-save —
    // the API rejects this with a 400. We still keep the toggled state in
    // the form so the user can pick a page.
    if (silenceMode === "page" && !silencePageId) {
      return;
    }

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

  // Auto-save when form data changes (debounced)
  useEffect(() => {
    if (!hasChanges || updateSilenceMutation.isPending) return;

    const timeoutId = setTimeout(() => {
      handleSave();
    }, 1000);

    return () => clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [silenceEnabled, silenceStartTime, silenceEndTime, silenceMode, silencePageId, silenceIndicatorText, silenceIndicatorPosition, hasChanges]);

  const isSaving = updateSilenceMutation.isPending || updatePollingMutation.isPending;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <CalendarClock className="h-4 w-4" />
          {t("title")}
        </CardTitle>
        <CardDescription>
          {t("description")}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="divide-y">
          {/* Polling Interval */}
          <div className="py-5 first:pt-0">
            {isLoadingPolling ? (
              <div className="space-y-3">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-10 w-32" />
                <Skeleton className="h-3 w-40" />
              </div>
            ) : (
              <div>
                <Label htmlFor="polling-interval" className="text-sm font-medium">{t("boardUpdateIntervalLabel")}</Label>
                <p className="text-xs text-muted-foreground mt-1 mb-3">{t("boardUpdateIntervalDescription")}</p>
                <div className="flex items-center gap-3">
                  <Input
                    id="polling-interval"
                    type="number"
                    min={10}
                    max={3600}
                    value={pollingInterval}
                    onChange={(e) => handlePollingIntervalChange(e.target.value)}
                    onBlur={handlePollingIntervalBlur}
                    disabled={isSaving}
                    className="w-32"
                  />
                  <span className="text-sm text-muted-foreground">{tc("seconds")}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-2">{t("requiresServiceRestart")}</p>
              </div>
            )}
          </div>

          {/* Board State Read Intervals */}
          <div className="py-5">
            {isLoadingPolling ? (
              <div className="space-y-3">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-10 w-32" />
              </div>
            ) : (
              <div className="space-y-4">
                {/* Local interval */}
                <div>
                  <Label htmlFor="board-read-local" className="text-sm font-medium">{t("boardReadIntervalLocalLabel")}</Label>
                  <p className="text-xs text-muted-foreground mt-1 mb-3">{t("boardReadIntervalLocalDescription")}</p>
                  <div className="flex items-center gap-3">
                    <Input
                      id="board-read-local"
                      type="number"
                      min={20}
                      max={3600}
                      value={boardReadIntervalLocal}
                      onChange={(e) => {
                        const v = parseInt(e.target.value, 10);
                        if (!isNaN(v)) setBoardReadIntervalLocal(v);
                      }}
                      onBlur={handleBoardReadIntervalLocalBlur}
                      disabled={updateBoardReadIntervalMutation.isPending}
                      className="w-32"
                    />
                    <span className="text-sm text-muted-foreground">{tc("seconds")}</span>
                  </div>
                </div>
                {/* Cloud interval */}
                <div>
                  <Label htmlFor="board-read-cloud" className="text-sm font-medium">{t("boardReadIntervalCloudLabel")}</Label>
                  <p className="text-xs text-muted-foreground mt-1 mb-3">{t("boardReadIntervalCloudDescription")}</p>
                  <div className="flex items-center gap-3">
                    <Input
                      id="board-read-cloud"
                      type="number"
                      min={20}
                      max={3600}
                      value={boardReadIntervalCloud}
                      onChange={(e) => {
                        const v = parseInt(e.target.value, 10);
                        if (!isNaN(v)) setBoardReadIntervalCloud(v);
                      }}
                      onBlur={handleBoardReadIntervalCloudBlur}
                      disabled={updateBoardReadIntervalMutation.isPending}
                      className="w-32"
                    />
                    <span className="text-sm text-muted-foreground">{tc("seconds")}</span>
                  </div>
                  {boardReadIntervalCloud < 60 && (
                    <p className="text-xs text-warning mt-2">{t("boardReadIntervalWarning")}</p>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Silence Schedule */}
          <div className="py-5 last:pb-0">
            {isLoadingSilence ? (
              <div className="space-y-3">
                <Skeleton className="h-5 w-11 rounded-full" />
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-3 w-48" />
              </div>
            ) : (
              <>
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <label htmlFor="silence-enabled" className="text-sm font-medium cursor-pointer">
                      {t("silenceScheduleLabel")}
                    </label>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {t("silenceScheduleDescription")}
                    </p>
                  </div>
                  <Switch
                    checked={silenceEnabled}
                    onCheckedChange={handleSilenceToggle}
                    disabled={isSaving}
                    id="silence-enabled"
                  />
                </div>

                {silenceEnabled && (
                  <div className="mt-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="silence-start" className="text-xs">{t("startTimeLabel")}</Label>
                        <TimePicker
                          id="silence-start"
                          value={silenceStartTime}
                          onChange={(val) => handleSilenceTimeChange("start", val)}
                          disabled={isSaving}
                        />
                        <p className="text-xs text-muted-foreground">{t("whenSilenceBegins")}</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="silence-end" className="text-xs">{t("endTimeLabel")}</Label>
                        <TimePicker
                          id="silence-end"
                          value={silenceEndTime}
                          onChange={(val) => handleSilenceTimeChange("end", val)}
                          disabled={isSaving}
                        />
                        <p className="text-xs text-muted-foreground">{t("whenSilenceEnds")}</p>
                      </div>
                    </div>

                    {/* Silence behaviour selector */}
                    <div className="mt-4 space-y-2">
                      <Label htmlFor="silence-mode" className="text-xs">
                        {t("silenceModeLabel")}
                      </Label>
                      <Select
                        value={silenceMode}
                        onValueChange={(val) =>
                          handleSilenceModeChange(val as SilenceMode)
                        }
                        disabled={isSaving}
                      >
                        <SelectTrigger id="silence-mode" className="w-full">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="indicator">
                            {t("silenceModeIndicator")}
                          </SelectItem>
                          <SelectItem value="freeze">
                            {t("silenceModeFreeze")}
                          </SelectItem>
                          <SelectItem value="page">
                            {t("silenceModePage")}
                          </SelectItem>
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
                      <div className="mt-3 space-y-2">
                        <Label htmlFor="silence-indicator-text" className="text-xs">
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
                        <p className="text-xs text-muted-foreground">
                          {t("silenceIndicatorTextHelp")}
                        </p>
                      </div>
                      <div className="mt-3 space-y-2">
                        <Label htmlFor="silence-indicator-position" className="text-xs">
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
                      <div className="mt-3 space-y-2">
                        <Label htmlFor="silence-page" className="text-xs">
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
                        <p className="text-xs text-muted-foreground">
                          {t("silencePageHelp")}
                        </p>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>

        {/* Auto-save indicator */}
        {isSaving && (
          <div className="flex items-center justify-center gap-2 pt-4 mt-4 border-t text-xs text-muted-foreground">
            <div className="h-3 w-3 animate-spin rounded-full border-2 border-primary border-t-transparent" />
            <span>{tc("savingIndicator")}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

