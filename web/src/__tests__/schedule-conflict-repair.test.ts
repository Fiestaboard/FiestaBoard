import { describe, expect, it } from "vitest";

import type { ScheduleEntry } from "@/lib/api";
import { weeklyConflictRepair } from "@/lib/schedule-conflict-repair";
const selected = {
  id: "selected",
  start_time: "12:00",
  end_time: "15:00",
  enabled: true,
  recurrence_type: "weekly",
} as ScheduleEntry;
const other = { ...selected, id: "other", start_time: "10:00", end_time: "13:00" };
const overlaps = [{ schedule1_id: "selected", schedule2_id: "other", conflict_description: "Overlap" }];
describe("Supported weekly conflict repair", () => {
  it("offers an explicit start shift past the other weekly entry's fixed end", () =>
    expect(weeklyConflictRepair(selected, [selected, other], overlaps)).toBe("13:00"));
  it("does not invent a fix for dated, solar or midnight ranges", () => {
    expect(
      weeklyConflictRepair({ ...selected, recurrence_type: "one_off_date" }, [selected, other], overlaps),
    ).toBeNull();
    expect(weeklyConflictRepair(selected, [selected, { ...other, end_type: "sunset" }], overlaps)).toBeNull();
    expect(
      weeklyConflictRepair(selected, [selected, { ...other, start_time: "23:00", end_time: "13:00" }], overlaps),
    ).toBeNull();
  });
});
