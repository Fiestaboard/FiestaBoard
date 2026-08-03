"use client";

import { Badge, Box, Text } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { Clock, Loader2, Moon, Sun } from "lucide-react";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { getTimezoneAbbreviation, utcToLocalTime } from "@/lib/timezone-utils";

interface SilenceModeStatusProps {
  className?: string;
  showDetails?: boolean;
}

export function SilenceModeStatus({ className, showDetails = true }: SilenceModeStatusProps) {
  const t = useTranslations("silenceMode");

  // Fetch general config for timezone
  const { data: generalConfig } = useQuery({
    queryKey: ["generalConfig"],
    queryFn: api.getGeneralConfig,
  });

  // Fetch silence status (poll every minute)
  const { data: silenceStatus, isLoading } = useQuery({
    queryKey: ["silenceStatus"],
    queryFn: api.getSilenceStatus,
    refetchInterval: 60000, // Poll every minute
  });

  if (isLoading || !silenceStatus || !generalConfig) {
    return (
      <Box className={className}>
        <Badge variant="secondary" className="gap-1.5">
          <Loader2 className="h-3 w-3 animate-spin" />
          {t("loading")}
        </Badge>
      </Box>
    );
  }

  if (!silenceStatus.enabled) {
    return (
      <Box className={className}>
        <Badge variant="outline" className="gap-1.5">
          <Moon className="h-3 w-3" />
          {t("disabled")}
        </Badge>
      </Box>
    );
  }

  const userTimezone = generalConfig.timezone || "America/Los_Angeles";
  const timezoneAbbr = getTimezoneAbbreviation(userTimezone);

  // Convert UTC times to local for display
  const _startLocal = utcToLocalTime(silenceStatus.start_time_utc, userTimezone);
  const _endLocal = utcToLocalTime(silenceStatus.end_time_utc, userTimezone);
  const nextChangeLocal = utcToLocalTime(silenceStatus.next_change_utc, userTimezone);

  if (silenceStatus.active) {
    return (
      <Box className={className}>
        <Badge variant="destructive" className="gap-1.5">
          <Moon className="h-3 w-3" />
          {t("active")}
        </Badge>
        {showDetails && (
          <Text tone="muted" size="xs" className="mt-1">
            <Clock className="h-3 w-3 inline mr-1" />
            {t("until", { time: nextChangeLocal, timezone: timezoneAbbr })}
          </Text>
        )}
      </Box>
    );
  }

  return (
    <Box className={className}>
      <Badge variant="secondary" className="gap-1.5">
        <Sun className="h-3 w-3" />
        {t("inactive")}
      </Badge>
      {showDetails && (
        <Text tone="muted" size="xs" className="mt-1">
          <Clock className="h-3 w-3 inline mr-1" />
          {t("startsAt", { time: nextChangeLocal, timezone: timezoneAbbr })}
        </Text>
      )}
    </Box>
  );
}

// Compact version for use in headers or tight spaces
export function SilenceModeStatusCompact({ className }: { className?: string }) {
  const t = useTranslations("silenceMode");
  const { data: silenceStatus } = useQuery({
    queryKey: ["silenceStatus"],
    queryFn: api.getSilenceStatus,
    refetchInterval: 60000,
  });

  if (!silenceStatus?.enabled) {
    return null;
  }

  return (
    <Badge variant={silenceStatus.active ? "destructive" : "secondary"} className={className}>
      {silenceStatus.active ? (
        <>
          <Moon className="h-3 w-3 mr-1" />
          {t("compactSilent")}
        </>
      ) : (
        <>
          <Sun className="h-3 w-3 mr-1" />
          {t("compactActive")}
        </>
      )}
    </Badge>
  );
}
