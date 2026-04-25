"use client";

import { useState, useEffect } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { DaySelector } from "@/components/day-selector";
import { AlertCircle, Loader2, Trash2, GalleryHorizontalEnd } from "lucide-react";
import type { ScheduleEntry, ScheduleCreate, ScheduleUpdate, DayPattern, Carousel } from "@/lib/api";

interface ScheduleEntryFormProps {
  schedule?: ScheduleEntry;
  pages: Array<{ id: string; name: string }>;
  carousels?: Carousel[];
  onSubmit: (data: ScheduleCreate | ScheduleUpdate) => Promise<void>;
  onCancel: () => void;
  onDelete?: () => void;
  prefillStartTime?: string;
  prefillEndTime?: string;
  prefillDayPattern?: DayPattern;
  prefillCustomDays?: string[];
}

// Generate 1-minute interval times for full scheduling flexibility
const generateTimeOptions = () => {
  const times: string[] = [];
  for (let hour = 0; hour < 24; hour++) {
    for (let minute = 0; minute < 60; minute++) {
      const h = hour.toString().padStart(2, "0");
      const m = minute.toString().padStart(2, "0");
      times.push(`${h}:${m}`);
    }
  }
  return times;
};

const TIME_OPTIONS = generateTimeOptions();

export function ScheduleEntryForm({
  schedule,
  pages,
  carousels = [],
  onSubmit,
  onCancel,
  onDelete,
  prefillStartTime,
  prefillEndTime,
  prefillDayPattern,
  prefillCustomDays,
}: ScheduleEntryFormProps) {
  const t = useTranslations("schedule");
  const tc = useTranslations("common");
  const isEdit = Boolean(schedule);
  
  // Use schedule values if editing, prefill values if creating from calendar, or defaults
  const [pageId, setPageId] = useState(schedule?.page_id || "");
  const [startTime, setStartTime] = useState(
    schedule?.start_time || prefillStartTime || "09:00"
  );
  const [endTime, setEndTime] = useState(
    schedule?.end_time || prefillEndTime || "17:00"
  );
  const [hasEndTime, setHasEndTime] = useState(
    schedule ? schedule.end_time != null : true
  );
  const [dayPattern, setDayPattern] = useState<DayPattern>(
    schedule?.day_pattern || prefillDayPattern || "all"
  );
  const [customDays, setCustomDays] = useState<string[]>(
    schedule?.custom_days || prefillCustomDays || []
  );
  const [enabled, setEnabled] = useState(schedule?.enabled !== false);
  
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Validation
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  
  useEffect(() => {
    const errors: string[] = [];
    
    if (!pageId) {
      errors.push(t("scheduleEntryForm.validationSelectPage"));
    }
    
    // Validate times are not identical (zero-duration schedule)
    // Note: endMinutes < startMinutes is valid (midnight rollover, e.g. 23:00-03:00)
    // Only check when end time is set
    if (hasEndTime) {
      const startMinutes = timeToMinutes(startTime);
      const endMinutes = timeToMinutes(endTime);
      if (startMinutes === endMinutes) {
        errors.push(t("scheduleEntryForm.validationEndTimeDifferent"));
      }
    }
    
    // Validate custom days
    if (dayPattern === "custom" && customDays.length === 0) {
      errors.push(t("scheduleEntryForm.validationSelectDay"));
    }
    
    setValidationErrors(errors);
  }, [pageId, startTime, endTime, hasEndTime, dayPattern, customDays]);

  const timeToMinutes = (time: string): number => {
    const [h, m] = time.split(":").map(Number);
    return h * 60 + m;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (validationErrors.length > 0) {
      return;
    }
    
    setIsSubmitting(true);
    setError(null);
    
    try {
      const data = {
        page_id: pageId,
        start_time: startTime,
        end_time: hasEndTime ? endTime : null,
        day_pattern: dayPattern,
        custom_days: dayPattern === "custom" ? customDays : undefined,
        enabled,
      };
      
      await onSubmit(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("scheduleEntryForm.submitError"));
      setIsSubmitting(false);
    }
  };

  const handleDayChange = (pattern: DayPattern, days?: string[]) => {
    setDayPattern(pattern);
    if (days) {
      setCustomDays(days);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      
      {/* Page / Carousel Selection */}
      <div className="space-y-2">
        <Label htmlFor="page">{t("scheduleEntryForm.pageOrCarousel")}</Label>
        <Select value={pageId} onValueChange={setPageId} modal={false}>
          <SelectTrigger id="page">
            <SelectValue placeholder={t("scheduleEntryForm.selectPageOrCarousel")} />
          </SelectTrigger>
          <SelectContent>
            {carousels.length > 0 && (
              <>
                <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground">{t("scheduleEntryForm.carouselsGroup")}</div>
                {carousels.map((carousel) => (
                  <SelectItem key={carousel.id} value={carousel.id}>
                    <span className="flex items-center gap-2">
                      <GalleryHorizontalEnd className="h-3.5 w-3.5" />
                      {carousel.name}
                    </span>
                  </SelectItem>
                ))}
                <div className="px-2 py-1.5 text-xs font-medium text-muted-foreground">{t("scheduleEntryForm.pagesGroup")}</div>
              </>
            )}
            {pages.map((page) => (
              <SelectItem key={page.id} value={page.id}>
                {page.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Time Selection */}
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="start-time">{t("scheduleEntryForm.startTime")}</Label>
            <Select value={startTime} onValueChange={setStartTime} modal={false}>
              <SelectTrigger id="start-time">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="max-h-60">
                {TIME_OPTIONS.map((time) => (
                  <SelectItem key={`start-${time}`} value={time}>
                    {time}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {hasEndTime && (
            <div className="space-y-2">
              <Label htmlFor="end-time">{t("scheduleEntryForm.endTime")}</Label>
              <Select value={endTime} onValueChange={setEndTime} modal={false}>
                <SelectTrigger id="end-time">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-60">
                  {TIME_OPTIONS.map((time) => (
                    <SelectItem key={`end-${time}`} value={time}>
                      {time}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}
        </div>

        {/* End time toggle */}
        <div className="flex items-center gap-2">
          <Switch
            id="has-end-time"
            checked={hasEndTime}
            onCheckedChange={setHasEndTime}
          />
          <Label htmlFor="has-end-time" className="text-sm text-muted-foreground">
            {t("scheduleEntryForm.setEndTime")}
          </Label>
          {!hasEndTime && (
            <span className="text-xs text-muted-foreground">
              ({t("scheduleEntryForm.openEndedHint")})
            </span>
          )}
        </div>
      </div>

      {/* Day Pattern Selection */}
      <DaySelector
        value={dayPattern}
        customDays={customDays}
        onChange={handleDayChange}
      />

      {/* Enabled Toggle */}
      <div className="flex items-center justify-between rounded-lg border p-4">
        <div className="space-y-0.5">
          <Label htmlFor="enabled" className="text-base">
            Enabled
          </Label>
          <div className="text-sm text-muted-foreground">
            Schedule will be active when enabled
          </div>
        </div>
        <Switch
          id="enabled"
          checked={enabled}
          onCheckedChange={setEnabled}
        />
      </div>

      {/* Validation Errors */}
      {validationErrors.length > 0 && (
        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            <ul className="list-disc list-inside space-y-1">
              {validationErrors.map((err, i) => (
                <li key={i}>{err}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      )}

      {/* Actions */}
      <div className="flex justify-between gap-2">
        <div>
          {isEdit && onDelete && (
            <Button
              type="button"
              variant="destructive"
              onClick={onDelete}
              disabled={isSubmitting}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              {tc("delete")}
            </Button>
          )}
        </div>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
            {tc("cancel")}
          </Button>
          <Button
            type="submit"
            disabled={validationErrors.length > 0 || isSubmitting}
          >
            {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {isEdit ? t("scheduleEntryForm.updateSchedule") : t("scheduleEntryForm.createSchedule")}
          </Button>
        </div>
      </div>
    </form>
  );
}
