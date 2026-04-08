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
import { AlertCircle, Loader2, Trash2, GalleryHorizontalEnd, Sunrise, Sunset } from "lucide-react";
import type { ScheduleEntry, ScheduleCreate, ScheduleUpdate, DayPattern, TimeType, Carousel } from "@/lib/api";

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

const TIME_TYPE_OPTIONS: TimeType[] = ["fixed", "sunrise", "sunset"];

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

  // Sun schedule state
  const [startType, setStartType] = useState<TimeType>(schedule?.start_type || "fixed");
  const [startSunOffset, setStartSunOffset] = useState<number>(schedule?.start_sun_offset || 0);
  const [endType, setEndType] = useState<TimeType>(schedule?.end_type || "fixed");
  const [endSunOffset, setEndSunOffset] = useState<number>(schedule?.end_sun_offset || 0);
  
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
    // Only check when both times are fixed and end time is set
    if (hasEndTime && startType === "fixed" && endType === "fixed") {
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
  }, [pageId, startTime, endTime, hasEndTime, dayPattern, customDays, startType, endType]);

  const timeToMinutes = (time: string): number => {
    const [h, m] = time.split(":").map(Number);
    return h * 60 + m;
  };

  const getTimeTypeLabel = (type: TimeType): string => {
    switch (type) {
      case "fixed": return t("scheduleEntryForm.timeTypeFixed");
      case "sunrise": return t("scheduleEntryForm.timeTypeSunrise");
      case "sunset": return t("scheduleEntryForm.timeTypeSunset");
    }
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
        start_type: startType,
        start_sun_offset: startType !== "fixed" ? startSunOffset : 0,
        end_type: endType,
        end_sun_offset: endType !== "fixed" ? endSunOffset : 0,
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
        {/* Start Time */}
        <div className="space-y-2">
          <Label>{t("scheduleEntryForm.startTime")}</Label>
          <div className="flex gap-2">
            <Select value={startType} onValueChange={(v) => setStartType(v as TimeType)}>
              <SelectTrigger className="w-[140px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {TIME_TYPE_OPTIONS.map((type) => (
                  <SelectItem key={`start-type-${type}`} value={type}>
                    <span className="flex items-center gap-1.5">
                      {type === "sunrise" && <Sunrise className="h-3.5 w-3.5" />}
                      {type === "sunset" && <Sunset className="h-3.5 w-3.5" />}
                      {getTimeTypeLabel(type)}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {startType === "fixed" ? (
              <Select value={startTime} onValueChange={setStartTime}>
                <SelectTrigger id="start-time" className="flex-1">
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
            ) : (
              <div className="flex items-center gap-2 flex-1">
                <Input
                  type="number"
                  value={startSunOffset}
                  onChange={(e) => {
                    const val = parseInt(e.target.value);
                    setStartSunOffset(isNaN(val) ? 0 : val);
                  }}
                  className="w-20"
                  aria-label={t("scheduleEntryForm.sunOffset")}
                />
                <span className="text-xs text-muted-foreground whitespace-nowrap">
                  {t("scheduleEntryForm.sunOffsetHint")}
                </span>
              </div>
            )}
          </div>
          {startType !== "fixed" && schedule?.resolved_start_time && (
            <p className="text-xs text-muted-foreground flex items-center gap-1">
              {startType === "sunrise" ? <Sunrise className="h-3 w-3" /> : <Sunset className="h-3 w-3" />}
              {t("scheduleEntryForm.resolvedTime", { time: schedule.resolved_start_time })}
            </p>
          )}
        </div>

        {/* End Time */}
        {hasEndTime && (
          <div className="space-y-2">
            <Label>{t("scheduleEntryForm.endTime")}</Label>
            <div className="flex gap-2">
              <Select value={endType} onValueChange={(v) => setEndType(v as TimeType)}>
                <SelectTrigger className="w-[140px]">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIME_TYPE_OPTIONS.map((type) => (
                    <SelectItem key={`end-type-${type}`} value={type}>
                      <span className="flex items-center gap-1.5">
                        {type === "sunrise" && <Sunrise className="h-3.5 w-3.5" />}
                        {type === "sunset" && <Sunset className="h-3.5 w-3.5" />}
                        {getTimeTypeLabel(type)}
                      </span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {endType === "fixed" ? (
                <Select value={endTime} onValueChange={setEndTime}>
                  <SelectTrigger id="end-time" className="flex-1">
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
              ) : (
                <div className="flex items-center gap-2 flex-1">
                  <Input
                    type="number"
                    value={endSunOffset}
                    onChange={(e) => {
                      const val = parseInt(e.target.value);
                      setEndSunOffset(isNaN(val) ? 0 : val);
                    }}
                    className="w-20"
                    aria-label={t("scheduleEntryForm.sunOffset")}
                  />
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    {t("scheduleEntryForm.sunOffsetHint")}
                  </span>
                </div>
              )}
            </div>
            {endType !== "fixed" && schedule?.resolved_end_time && (
              <p className="text-xs text-muted-foreground flex items-center gap-1">
                {endType === "sunrise" ? <Sunrise className="h-3 w-3" /> : <Sunset className="h-3 w-3" />}
                {t("scheduleEntryForm.resolvedTime", { time: schedule.resolved_end_time })}
              </p>
            )}
          </div>
        )}

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
