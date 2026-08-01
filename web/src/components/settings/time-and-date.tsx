"use client";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { formatInTimeZone } from "date-fns-tz";
import { Clock } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { TimezonePicker } from "@/components/ui/timezone-picker";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

type TimeFormat = "12h" | "24h";
type DateFormat = "MM/DD/YYYY" | "DD/MM/YYYY" | "YYYY-MM-DD";

export function TimeAndDateCard() {
  const t = useTranslations("profile");
  const queryClient = useQueryClient();

  const [timezone, setTimezone] = useState("America/Los_Angeles");
  const [timeFormat, setTimeFormat] = useState<TimeFormat>("12h");
  const [dateFormat, setDateFormat] = useState<DateFormat>("MM/DD/YYYY");

  const { data: allSettings, isLoading } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  useEffect(() => {
    const general = allSettings?.general;
    if (general) {
      setTimezone(general.timezone ?? "America/Los_Angeles");
      setTimeFormat((general.time_format as TimeFormat) ?? "12h");
      setDateFormat((general.date_format as DateFormat) ?? "MM/DD/YYYY");
    }
  }, [allSettings?.general]);

  const updateMutation = useMutation({
    mutationFn: api.updateGeneralConfig,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["all-settings"] }),
    onError: (error: Error) => toast.error(error.message),
  });

  const handleTimezoneChange = (value: string) => {
    setTimezone(value);
    updateMutation.mutate({ timezone: value });
  };

  const handleTimeFormatChange = (value: TimeFormat) => {
    setTimeFormat(value);
    updateMutation.mutate({ time_format: value });
  };

  const handleDateFormatChange = (value: DateFormat) => {
    setDateFormat(value);
    updateMutation.mutate({ date_format: value });
  };

  const getFormatPreview = () => {
    try {
      const now = new Date();
      const timeStr =
        timeFormat === "24h" ? formatInTimeZone(now, timezone, "HH:mm") : formatInTimeZone(now, timezone, "h:mm a");
      const dateFmt =
        dateFormat === "DD/MM/YYYY" ? "dd/MM/yyyy" : dateFormat === "YYYY-MM-DD" ? "yyyy-MM-dd" : "MM/dd/yyyy";
      const dateStr = formatInTimeZone(now, timezone, dateFmt);
      return t("dateFormatPreview", { time: timeStr, date: dateStr });
    } catch {
      return null;
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Clock className="h-4 w-4" />
          {t("timeAndDateTitle")}
        </CardTitle>
        <CardDescription>{t("timeAndDateDescription")}</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-4">
            <Skeleton className="h-10 w-full max-w-sm" />
            <Skeleton className="h-10 w-48" />
            <Skeleton className="h-10 w-48" />
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-2 max-w-sm">
              <Label id="timezone-label" htmlFor="timezone-picker" className="text-sm font-medium">
                {t("timezoneLabel")}
              </Label>
              <TimezonePicker id="timezone-picker" value={timezone} onChange={handleTimezoneChange} />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-md">
              <div className="space-y-2">
                <Label htmlFor="time-format" className="text-sm font-medium">
                  {t("timeFormat")}
                </Label>
                <Select
                  value={timeFormat}
                  onValueChange={(v) => handleTimeFormatChange(v as TimeFormat)}
                  disabled={updateMutation.isPending}
                >
                  <SelectTrigger id="time-format">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="12h">{t("timeFormat12h")}</SelectItem>
                    <SelectItem value="24h">{t("timeFormat24h")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label htmlFor="date-format" className="text-sm font-medium">
                  {t("dateFormat")}
                </Label>
                <Select
                  value={dateFormat}
                  onValueChange={(v) => handleDateFormatChange(v as DateFormat)}
                  disabled={updateMutation.isPending}
                >
                  <SelectTrigger id="date-format">
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

            {(() => {
              const preview = getFormatPreview();
              return preview ? <p className="text-xs text-muted-foreground">{preview}</p> : null;
            })()}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
