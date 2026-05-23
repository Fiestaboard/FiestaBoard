"use client";

import { UpdateIntervals } from "@/components/settings/update-intervals";
import { SilenceSchedule } from "@/components/settings/silence-schedule";

export function GeneralSettings() {
  return (
    <div className="space-y-6">
      <UpdateIntervals />
      <SilenceSchedule />
    </div>
  );
}
