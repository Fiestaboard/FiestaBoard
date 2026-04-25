"use client";

import { useState, useEffect, useCallback } from "react";
import { useTheme } from "next-themes";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { formatInTimeZone } from "date-fns-tz";
import {
  User,
  Sun,
  Moon,
  Monitor,
  Check,
  Globe,
  Accessibility,
  Info,
  Package,
  ExternalLink,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PageLayout } from "@/components/page-layout";
import { PageHeader } from "@/components/page-header";
import { LanguageSelector } from "@/components/language-selector";
import { api } from "@/lib/api";
import { useStatus } from "@/hooks/use-board";
import { useFormatPreferences } from "@/hooks/use-format-preferences";
import { TimezonePicker } from "@/components/ui/timezone-picker";
import { cn } from "@/lib/utils";
import { toast } from "sonner";

export default function ProfilePage() {
  const t = useTranslations("profile");
  const { theme, setTheme } = useTheme();
  const { timeFormat: _timeFormat, dateFormat: _dateFormat } = useFormatPreferences();
  const queryClient = useQueryClient();

  // ── Local state ──────────────────────────────────────────────────────────
  const [instanceName, setInstanceName] = useState("");
  const [timezone, setTimezone] = useState("America/Los_Angeles");
  const [selectedTimeFormat, setSelectedTimeFormat] = useState<"12h" | "24h">("12h");
  const [selectedDateFormat, setSelectedDateFormat] = useState<
    "MM/DD/YYYY" | "DD/MM/YYYY" | "YYYY-MM-DD"
  >("MM/DD/YYYY");
  const [reduceMotion, setReduceMotion] = useState(false);

  // ── Data fetching ─────────────────────────────────────────────────────────
  const { data: allSettings, isLoading: isLoadingSettings } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  const { data: versionData, isLoading: isLoadingVersion } = useQuery({
    queryKey: ["version"],
    queryFn: () => api.getVersion(),
    staleTime: Infinity,
    retry: false,
  });

  const { data: updateCheck } = useQuery({
    queryKey: ["update-check"],
    queryFn: () => api.checkForUpdate(),
    staleTime: 1000 * 60 * 60,
    retry: false,
  });

  const { data: statusData, isLoading: isLoadingStatus } = useStatus();

  // ── Sync from API ─────────────────────────────────────────────────────────
  useEffect(() => {
    const general = allSettings?.general;
    if (general) {
      setInstanceName(general.instance_name ?? "");
      setTimezone(general.timezone ?? "America/Los_Angeles");
      setSelectedTimeFormat((general.time_format as "12h" | "24h") ?? "12h");
      setSelectedDateFormat(
        (general.date_format as "MM/DD/YYYY" | "DD/MM/YYYY" | "YYYY-MM-DD") ?? "MM/DD/YYYY"
      );
    }
  }, [allSettings?.general]);

  useEffect(() => {
    const display = allSettings?.display;
    if (display) {
      setReduceMotion(display.reduce_motion ?? false);
    }
  }, [allSettings?.display]);

  // ── Mutations ─────────────────────────────────────────────────────────────
  const updateGeneralMutation = useMutation({
    mutationFn: api.updateGeneralConfig,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const updateDisplayMutation = useMutation({
    mutationFn: (settings: { reduce_motion: boolean }) => api.updateDisplaySettings(settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  // ── Handlers ──────────────────────────────────────────────────────────────
  const handleInstanceNameBlur = useCallback(() => {
    const current = allSettings?.general?.instance_name ?? "";
    if (instanceName !== current) {
      updateGeneralMutation.mutate({ instance_name: instanceName });
    }
  }, [instanceName, allSettings?.general?.instance_name, updateGeneralMutation]);

  const handleTimezoneChange = (value: string) => {
    setTimezone(value);
    updateGeneralMutation.mutate({ timezone: value });
  };

  const handleTimeFormatChange = (value: "12h" | "24h") => {
    setSelectedTimeFormat(value);
    updateGeneralMutation.mutate({ time_format: value });
  };

  const handleDateFormatChange = (value: "MM/DD/YYYY" | "DD/MM/YYYY" | "YYYY-MM-DD") => {
    setSelectedDateFormat(value);
    updateGeneralMutation.mutate({ date_format: value });
  };

  const handleReduceMotionToggle = (checked: boolean) => {
    setReduceMotion(checked);
    updateDisplayMutation.mutate({ reduce_motion: checked });
  };

  // ── Format preview ────────────────────────────────────────────────────────
  const getFormatPreview = () => {
    try {
      const now = new Date();
      const timeStr = selectedTimeFormat === "24h"
        ? formatInTimeZone(now, timezone, "HH:mm")
        : formatInTimeZone(now, timezone, "h:mm a");
      const dateFmt =
        selectedDateFormat === "DD/MM/YYYY"
          ? "dd/MM/yyyy"
          : selectedDateFormat === "YYYY-MM-DD"
            ? "yyyy-MM-dd"
            : "MM/dd/yyyy";
      const dateStr = formatInTimeZone(now, timezone, dateFmt);
      return t("dateFormatPreview", { time: timeStr, date: dateStr });
    } catch {
      return null;
    }
  };

  const isRunning = statusData?.running ?? false;
  const isSaving = updateGeneralMutation.isPending || updateDisplayMutation.isPending;

  return (
    <PageLayout>
      <PageHeader icon={User} title={t("title")} description={t("description")} />

      <div className="space-y-6">
        {/* ── 1. Your FiestaBoard ──────────────────────────────────────────── */}
        <div className="animate-card-fade-in" style={{ animationDelay: "0ms" }}>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("instanceNameTitle")}</CardTitle>
              <CardDescription>{t("instanceNameDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoadingSettings ? (
                <Skeleton className="h-10 w-full max-w-sm" />
              ) : (
                <div className="space-y-2 max-w-sm">
                  <Input
                    value={instanceName}
                    onChange={(e) => setInstanceName(e.target.value)}
                    onBlur={handleInstanceNameBlur}
                    placeholder={t("instanceNamePlaceholder")}
                    maxLength={50}
                  />
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── 2. Appearance ────────────────────────────────────────────────── */}
        <div className="animate-card-fade-in" style={{ animationDelay: "80ms" }}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Sun className="h-4 w-4 text-muted-foreground" />
                {t("appearanceTitle")}
              </CardTitle>
              <CardDescription>{t("appearanceDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-3 max-w-sm">
                {(
                  [
                    { value: "light", label: t("lightMode"), Icon: Sun },
                    { value: "dark", label: t("darkMode"), Icon: Moon },
                    { value: "system", label: t("systemMode"), Icon: Monitor },
                  ] as const
                ).map(({ value, label, Icon }) => {
                  const isActive = theme === value;
                  return (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setTheme(value)}
                      className={cn(
                        "relative flex flex-col items-center gap-2 rounded-lg border p-3 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                        isActive
                          ? "border-primary bg-primary/5 text-primary"
                          : "border-border hover:border-primary/50 hover:bg-accent"
                      )}
                      aria-pressed={isActive}
                    >
                      {isActive && (
                        <span className="absolute right-1.5 top-1.5">
                          <Check className="h-3 w-3 text-primary" />
                        </span>
                      )}
                      <Icon className="h-5 w-5" />
                      {label}
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        </div>

        {/* ── 3. Language ──────────────────────────────────────────────────── */}
        <div className="animate-card-fade-in" style={{ animationDelay: "160ms" }}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Globe className="h-4 w-4 text-muted-foreground" />
                {t("languageTitle")}
              </CardTitle>
              <CardDescription>{t("languageDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              <LanguageSelector />
            </CardContent>
          </Card>
        </div>

        {/* ── 4. Time & Date ───────────────────────────────────────────────── */}
        <div className="animate-card-fade-in" style={{ animationDelay: "240ms" }}>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("timeAndDateTitle")}</CardTitle>
              <CardDescription>{t("timeAndDateDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoadingSettings ? (
                <div className="space-y-4">
                  <Skeleton className="h-10 w-full max-w-sm" />
                  <Skeleton className="h-10 w-48" />
                  <Skeleton className="h-10 w-48" />
                </div>
              ) : (
                <div className="space-y-4">
                  {/* Timezone */}
                  <div className="space-y-2 max-w-sm">
                    <Label className="text-sm font-medium">{t("timezoneLabel")}</Label>
                    <TimezonePicker value={timezone} onChange={handleTimezoneChange} />
                  </div>

                  {/* Format selects */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-md">
                    <div className="space-y-2">
                      <Label className="text-sm font-medium">{t("timeFormat")}</Label>
                      <Select
                        value={selectedTimeFormat}
                        onValueChange={(v) => handleTimeFormatChange(v as "12h" | "24h")}
                        disabled={isSaving}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="12h">{t("timeFormat12h")}</SelectItem>
                          <SelectItem value="24h">{t("timeFormat24h")}</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <div className="space-y-2">
                      <Label className="text-sm font-medium">{t("dateFormat")}</Label>
                      <Select
                        value={selectedDateFormat}
                        onValueChange={(v) =>
                          handleDateFormatChange(
                            v as "MM/DD/YYYY" | "DD/MM/YYYY" | "YYYY-MM-DD"
                          )
                        }
                        disabled={isSaving}
                      >
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="MM/DD/YYYY">{t("dateFormatMMDDYYYY")}</SelectItem>
                          <SelectItem value="DD/MM/YYYY">{t("dateFormatDDMMYYYY")}</SelectItem>
                          <SelectItem value="YYYY-MM-DD">{t("dateFormatISO")}</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>
                  </div>

                  {/* Live preview */}
                  {(() => {
                    const preview = getFormatPreview();
                    return preview ? (
                      <p className="text-xs text-muted-foreground">{preview}</p>
                    ) : null;
                  })()}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── 5. Accessibility ─────────────────────────────────────────────── */}
        <div className="animate-card-fade-in" style={{ animationDelay: "320ms" }}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Accessibility className="h-4 w-4 text-muted-foreground" />
                {t("accessibilityTitle")}
              </CardTitle>
              <CardDescription>{t("accessibilityDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              {isLoadingSettings ? (
                <Skeleton className="h-6 w-48" />
              ) : (
                <div className="flex items-center gap-3">
                  <Switch
                    id="reduce-motion"
                    checked={reduceMotion}
                    onCheckedChange={handleReduceMotionToggle}
                    disabled={updateDisplayMutation.isPending}
                  />
                  <div>
                    <label htmlFor="reduce-motion" className="text-sm font-medium cursor-pointer">
                      {t("reduceMotion")}
                    </label>
                    <p className="text-xs text-muted-foreground mt-0.5">{t("reduceMotionHint")}</p>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* ── 6. About ─────────────────────────────────────────────────────── */}
        <div className="animate-card-fade-in" style={{ animationDelay: "400ms" }}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Info className="h-4 w-4 text-muted-foreground" />
                {t("aboutTitle")}
              </CardTitle>
              <CardDescription>{t("aboutDescription")}</CardDescription>
            </CardHeader>
            <CardContent>
              <dl className="space-y-3 text-sm">
                {/* Service status */}
                <div className="flex items-center justify-between gap-4">
                  <dt className="text-muted-foreground">{t("status")}</dt>
                  <dd>
                    {isLoadingStatus ? (
                      <Skeleton className="h-5 w-16" />
                    ) : (
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            "h-2 w-2 rounded-full",
                            isRunning ? "bg-board-green" : "bg-muted-foreground"
                          )}
                          style={
                            isRunning
                              ? {
                                  boxShadow:
                                    "0 0 6px color-mix(in oklch, var(--color-board-green) 50%, transparent)",
                                }
                              : undefined
                          }
                        />
                        <Badge
                          variant={isRunning ? "default" : "secondary"}
                          className={cn(
                            "text-xs",
                            isRunning &&
                              "bg-brand/15 text-brand border-brand/25 hover:bg-brand/20"
                          )}
                        >
                          {isRunning ? t("statusRunning") : t("statusStopped")}
                        </Badge>
                      </div>
                    )}
                  </dd>
                </div>

                {/* Version */}
                <div className="flex items-center justify-between gap-4">
                  <dt className="text-muted-foreground">{t("version")}</dt>
                  <dd>
                    {isLoadingVersion ? (
                      <Skeleton className="h-5 w-16" />
                    ) : versionData ? (
                      <div className="flex items-center gap-2">
                        <Package className="h-3.5 w-3.5 text-muted-foreground" />
                        <span className="font-mono tabular-nums">
                          v{versionData.package_version}
                        </span>
                        {versionData.is_dev && (
                          <Badge variant="secondary" className="text-xs">
                            {t("devBuild")}
                          </Badge>
                        )}
                        {updateCheck?.update_available && (
                          <Badge variant="outline" className="text-xs text-warning border-warning/50">
                            v{updateCheck.latest_version} available
                          </Badge>
                        )}
                      </div>
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </dd>
                </div>

                {/* Build */}
                {versionData?.build_version && (
                  <div className="flex items-center justify-between gap-4">
                    <dt className="text-muted-foreground">{t("buildVersion")}</dt>
                    <dd className="font-mono text-xs text-muted-foreground tabular-nums">
                      {versionData.build_version}
                    </dd>
                  </div>
                )}

                {/* Docs link */}
                <div className="pt-2 border-t">
                  <a
                    href="https://fiestaboard.app/docs/intro"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline"
                  >
                    {t("viewDocs")}
                    <ExternalLink className="h-3.5 w-3.5" />
                  </a>
                </div>
              </dl>
            </CardContent>
          </Card>
        </div>
      </div>
    </PageLayout>
  );
}
