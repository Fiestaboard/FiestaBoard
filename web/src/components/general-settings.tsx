"use client";

import { useState, useEffect, useDeferredValue } from "react";
import { useTranslations } from "next-intl";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { TimePicker } from "@/components/ui/time-picker";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { Settings } from "lucide-react";
import { api } from "@/lib/api";
import { TimezonePicker } from "@/components/ui/timezone-picker";
import { LanguageSelector } from "@/components/language-selector";
import { formatInTimeZone } from "date-fns-tz";
import { useStatus } from "@/hooks/use-board";
import { utcToLocalTime, localTimeToUTC } from "@/lib/timezone-utils";

export function GeneralSettings() {
  const t = useTranslations("generalSettings");
  const tc = useTranslations("common");
  const queryClient = useQueryClient();
  const [hasChanges, setHasChanges] = useState(false);
  const [timezone, setTimezone] = useState("America/Los_Angeles");
  const [silenceEnabled, setSilenceEnabled] = useState(false);
  const [silenceStartTime, setSilenceStartTime] = useState("20:00");
  const [silenceEndTime, setSilenceEndTime] = useState("07:00");
  const [pollingInterval, setPollingInterval] = useState(15);
  const [reduceMotion, setReduceMotion] = useState(false);

  // Fetch all settings in one request
  const { data: allSettings, isLoading: isLoadingSettings } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  // Extract individual settings from consolidated response
  const generalConfig = allSettings?.general;
  const silenceConfig = allSettings?.silence_schedule;
  const pollingSettings = allSettings?.polling;
  const displaySettings = allSettings?.display;
  const status = allSettings?.status;

  // Use deferred values for non-critical data to reduce re-render priority
  const deferredSilenceConfig = useDeferredValue(silenceConfig);
  const deferredPollingSettings = useDeferredValue(pollingSettings);
  const deferredDisplaySettings = useDeferredValue(displaySettings);
  
  // Compute loading states
  const isLoadingConfig = isLoadingSettings;
  const isLoadingSilence = isLoadingSettings;
  const isLoadingPolling = isLoadingSettings;
  const isLoadingStatus = isLoadingSettings;

  // Initialize form data when config loads
  useEffect(() => {
    if (generalConfig) {
      setTimezone(generalConfig.timezone || "America/Los_Angeles");
    }
  }, [generalConfig]);

  // Initialize silence schedule when config loads
  useEffect(() => {
    if (deferredSilenceConfig?.config && generalConfig?.timezone) {
      const userTimezone = generalConfig.timezone;
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

  // Initialize reduce motion when settings load
  useEffect(() => {
    if (deferredDisplaySettings) {
      setReduceMotion(deferredDisplaySettings.reduce_motion ?? false);
    }
  }, [deferredDisplaySettings]);

  // Update general config mutation
  const updateGeneralMutation = useMutation({
    mutationFn: api.updateGeneralConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["generalConfig"] });
      queryClient.invalidateQueries({ queryKey: ["config"] });
      toast.success(t("toastSettingsSaved"));
    },
    onError: (error: Error) => {
      toast.error(t("toastSettingsSaveFailed", { error: error.message }));
    },
  });

  // Update silence schedule mutation (now uses plugin API)
  const updateSilenceMutation = useMutation({
    mutationFn: (data: Record<string, unknown>) => 
      api.updatePluginConfig("silence_schedule", data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["plugin", "silence_schedule"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["plugins"], refetchType: 'active' });
      queryClient.invalidateQueries({ queryKey: ["config"], refetchType: 'active' });
      // Invalidate template variables since plugin config may affect available variables
      queryClient.invalidateQueries({ queryKey: ["template-variables"], refetchType: 'active' });
      toast.success(t("toastSettingsSaved"));
    },
    onError: (error: Error) => {
      toast.error(t("toastSilenceSaveFailed", { error: error.message }));
    },
  });

  // Update display settings mutation
  const updateDisplayMutation = useMutation({
    mutationFn: (settings: { reduce_motion: boolean }) => api.updateDisplaySettings(settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
      toast.success(t("toastDisplaySaved"));
    },
    onError: (error: Error) => {
      toast.error(t("toastDisplaySaveFailed", { error: error.message }));
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

  const handleReduceMotionToggle = (checked: boolean) => {
    setReduceMotion(checked);
    updateDisplayMutation.mutate({ reduce_motion: checked });
  };

  const handleTimezoneChange = (newTimezone: string) => {
    setTimezone(newTimezone);
    setHasChanges(true);
  };

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
    const promises = [];
    
    // Save timezone if changed
    promises.push(
      updateGeneralMutation.mutateAsync({ timezone })
    );
    
    // Save silence schedule if changed
    const startUtc = localTimeToUTC(silenceStartTime, timezone);
    const endUtc = localTimeToUTC(silenceEndTime, timezone);
    
    if (startUtc && endUtc) {
      promises.push(
        updateSilenceMutation.mutateAsync({
          enabled: silenceEnabled,
          start_time: startUtc,
          end_time: endUtc,
        })
      );
    }
    
    await Promise.all(promises);
    setHasChanges(false);
  };

  // Auto-save when form data changes (debounced)
  useEffect(() => {
    // Skip if no changes or if mutations are already in progress
    if (!hasChanges || updateGeneralMutation.isPending || updateSilenceMutation.isPending) {
      return;
    }

    // Debounce auto-save by 1 second
    const timeoutId = setTimeout(() => {
      handleSave();
    }, 1000);

    return () => clearTimeout(timeoutId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timezone, silenceEnabled, silenceStartTime, silenceEndTime, hasChanges]);

  // Get current time in selected timezone for display
  const getCurrentTimeInTimezone = () => {
    try {
      const now = new Date();
      return formatInTimeZone(now, timezone, "h:mm:ss a zzz");
    } catch {
      return "Invalid timezone";
    }
  };

  const isRunning = status?.running ?? false;
  const isSaving = updateGeneralMutation.isPending || updateSilenceMutation.isPending || updatePollingMutation.isPending || updateDisplayMutation.isPending;

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Settings className="h-5 w-5 text-muted-foreground" />
              {t("title")}
            </CardTitle>
            <CardDescription>
              {t("description")}
            </CardDescription>
          </div>
          {isLoadingStatus ? (
            <Skeleton className="h-5 w-20" />
          ) : (
            <Badge variant={isRunning ? "default" : "secondary"} className={`text-xs ${isRunning ? "bg-brand/15 text-brand border-brand/25 hover:bg-brand/20" : ""}`}>
              {isRunning ? tc("running") : tc("stopped")}
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <div className="divide-y">
          {/* Language */}
          <div className="py-5 first:pt-0">
            <Label className="text-sm font-medium">{t("languageLabel")}</Label>
            <p className="text-xs text-muted-foreground mt-1 mb-3">{t("languageDescription")}</p>
            <LanguageSelector />
          </div>

          {/* Reduce Motion */}
          <div className="py-5">
            <div className="flex items-center gap-3">
              <Switch
                checked={reduceMotion}
                onCheckedChange={handleReduceMotionToggle}
                disabled={isSaving}
                id="reduce-motion"
              />
              <div>
                <label htmlFor="reduce-motion" className="text-sm font-medium cursor-pointer">
                  {t("reduceMotionLabel")}
                </label>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {t("reduceMotionDescription")}
                </p>
              </div>
            </div>
          </div>

          {/* Timezone & Polling Interval */}
          <div className="py-5">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Timezone */}
              {isLoadingConfig ? (
                <div className="space-y-3">
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-3 w-full" />
                  <Skeleton className="h-10 w-full" />
                  <Skeleton className="h-3 w-48" />
                </div>
              ) : (
                <div>
                  <Label htmlFor="timezone" className="text-sm font-medium">{t("timezoneLabel")}</Label>
                  <p className="text-xs text-muted-foreground mt-1 mb-3">{t("timezoneDescription")}</p>
                  <TimezonePicker
                    value={timezone}
                    onChange={handleTimezoneChange}
                  />
                  <p className="text-xs text-muted-foreground mt-2">
                    {t("currentTime", { time: getCurrentTimeInTimezone() })}
                  </p>
                </div>
              )}

              {/* Polling Interval */}
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
                          value={silenceStartTime}
                          onChange={(val) => handleSilenceTimeChange("start", val)}
                          disabled={isSaving}
                        />
                        <p className="text-xs text-muted-foreground">{t("whenSilenceBegins")}</p>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="silence-end" className="text-xs">{t("endTimeLabel")}</Label>
                        <TimePicker
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

