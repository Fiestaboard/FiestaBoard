"use client";

import { SilenceSchedule } from "@/components/settings/silence-schedule";
import { UpdateIntervals } from "@/components/settings/update-intervals";

export function GeneralSettings() {
  return (
    <div className="space-y-6">
      <UpdateIntervals />
      <SilenceSchedule />
    </div>
  );
}
