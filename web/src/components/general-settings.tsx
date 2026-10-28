"use client";

import { Stack } from "@fiestaboard/ui";

import { SilenceSchedule } from "@/components/settings/silence-schedule";
import { UpdateIntervals } from "@/components/settings/update-intervals";
import type { BoardInstance } from "@/lib/api";

export function GeneralSettings({ board }: { board: BoardInstance }) {
  return (
    <Stack gap="6">
      <UpdateIntervals board={board} />
      <SilenceSchedule boardId={board.id} />
    </Stack>
  );
}
