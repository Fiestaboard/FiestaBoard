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
import { toast } from "sonner";
import { CalendarClock } from "lucide-react";
import { api } from "@/lib/api";
import { utcToLocalTime, localTimeToUTC } from "@/lib/timezone-utils";

export function GeneralSettings() {
  const t = useTranslations("generalSettings");
  const tc = useTranslations("common");
  const queryClient = useQueryClient();
  const [hasChanges, setHasChanges] = useState(false);
  const [silenceEnabled, setSilenceEnabled] = useState(false);
  const [silenceStartTime, setSilenceStartTime] = useState("20:00");
  const [silenceEndTime, setSilenceEndTime] = useState("07:00");
  const [pollingInterval, setPollingInterval] = useState(15);

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
      
      setHasChanges(false);
    }
  }, [deferredSilenceConfig, generalConfig?.timezone]);

  // Initialize polling interval when settings load
  useEffect(() => {
    if (deferredPollingSettings) {
      setPollingInterval(deferredPollingSettings.interval_seconds);
    }
  }, [deferredPollingSettings]);

  // Update silence schedule mutation (system feature endpoint, not plugin API)
  const updateSilenceMutation = useMutation({
    mutationFn: (data: { enabled: boolean; start_time: string; end_time: string }) =>
      api.updateSilenceSchedule(data),
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
    mutationFn: (interval: number) => api.updatePollingSettings(interval),
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

  const handlePollingIntervalChange = (value: string) => {
    const interval = parseInt(value, 10);
    if (!isNaN(interval) && interval >= 10) {
      setPollingInterval(interval);
      setHasChanges(true);
    }
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

  const handleSave = async () => {
    const timezone = generalConfig?.timezone ?? "America/Los_Angeles";
    const startUtc = localTimeToUTC(silenceStartTime, timezone);
    const endUtc = localTimeToUTC(silenceEndTime, timezone);

    if (startUtc && endUtc) {
      await updateSilenceMutation.mutateAsync({
        enabled: silenceEnabled,
        start_time: startUtc,
        end_time: endUtc,
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
  }, [silenceEnabled, silenceStartTime, silenceEndTime, hasChanges]);

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
                    disabled={isSaving}
                    className="w-32"
                  />
                  <span className="text-sm text-muted-foreground">{tc("seconds")}</span>
                </div>
                <p className="text-xs text-muted-foreground mt-2">{t("requiresServiceRestart")}</p>
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
                <div className="flex items-center gap-3">
                  <Switch
                    checked={silenceEnabled}
                    onCheckedChange={handleSilenceToggle}
                    disabled={isSaving}
                    id="silence-enabled"
                  />
                  <div>
                    <label htmlFor="silence-enabled" className="text-sm font-medium cursor-pointer">
                      {t("silenceScheduleLabel")}
                    </label>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {t("silenceScheduleDescription")}
                    </p>
                  </div>
                </div>

                {silenceEnabled && (
                  <div className="mt-4 ml-[52px]">
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

