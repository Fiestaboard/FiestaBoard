"use client";

import { Box, Flex, PageSection, Skeleton, Switch, Text } from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

/**
 * Settings → Behavior → how the schedule on/off toggle behaves.
 *
 * Turning schedule mode back on normally repaints the board at once, because
 * the active page is re-resolved from the clock on every polling pass. Users
 * who toggle the schedule from an automation (Home Assistant, a wall switch)
 * often want the opposite: leave the board alone until the schedule reaches
 * its next window. This card exposes that choice; it is off by default.
 */
export function ScheduleBehavior() {
  const t = useTranslations("generalSettings");
  const queryClient = useQueryClient();

  const [deferOnReenable, setDeferOnReenable] = useState(false);

  const { data: allSettings, isLoading } = useQuery({
    queryKey: ["all-settings"],
    queryFn: api.getAllSettings,
  });

  // Mirror the server value during render rather than in an effect, so the
  // switch never commits the default `false` first and then flip (#1568).
  const schedule = allSettings?.schedule;
  if (useDepsChanged([schedule]) && schedule) {
    setDeferOnReenable(schedule.defer_on_reenable ?? false);
  }

  const updateMutation = useMutation({
    mutationFn: (defer: boolean) => api.setScheduleSettings({ defer_on_reenable: defer }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["all-settings"] }),
    onError: (error: Error) => toast.error(error.message),
  });

  const handleToggle = (checked: boolean) => {
    setDeferOnReenable(checked);
    updateMutation.mutate(checked);
  };

  return (
    <PageSection
      icon={<CalendarClock />}
      title={t("scheduleBehaviorTitle")}
      description={t("scheduleBehaviorDescription")}
    >
      {isLoading ? (
        <Skeleton className="h-6 w-48" />
      ) : (
        <Flex align="center" gap="3">
          <Switch
            id="schedule-defer-on-reenable"
            checked={deferOnReenable}
            onCheckedChange={handleToggle}
            disabled={updateMutation.isPending}
          />
          <Box>
            <label htmlFor="schedule-defer-on-reenable" className="text-sm font-medium cursor-pointer">
              {t("deferOnReenable")}
            </label>
            <Text size="xs" tone="muted" className="mt-0.5">
              {t("deferOnReenableHint")}
            </Text>
          </Box>
        </Flex>
      )}
    </PageSection>
  );
}
