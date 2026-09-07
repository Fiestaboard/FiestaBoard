"use client";

import { Stack } from "@fiestaboard/ui";

import { SilenceSchedule } from "@/components/settings/silence-schedule";
import { UpdateIntervals } from "@/components/settings/update-intervals";

export function GeneralSettings() {
  return (
    <Stack gap="6">
      <UpdateIntervals />
      <SilenceSchedule />
    </Stack>
  );
}
