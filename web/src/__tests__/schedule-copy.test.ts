import { afterEach, describe, expect, it, vi } from "vitest";

import { api, type BoardInstance, type Page, type ScheduleEntry, type ScheduleWriteResponse } from "@/lib/api";
import { copyScheduleEntries } from "@/lib/schedule-copy";
const target = { id: "secondary", device_type: "note" } as BoardInstance;
const pages = [
  { id: "small", device_type: "note" },
  { id: "big", device_type: "flagship" },
] as Page[];
const entry = {
  id: "source-entry",
  page_id: "small",
  start_time: "09:00",
  end_time: "13:00",
  day_pattern: "all",
  enabled: true,
  recurrence_type: "one_off_date",
  one_off_date: "2026-11-18",
  revision: "source-revision",
} as ScheduleEntry;
afterEach(() => vi.restoreAllMocks());
describe("Copy an empty display's schedule", () => {
  it("copies recurrence fields with fresh IDs to the explicit target display", async () => {
    const create = vi
      .spyOn(api, "createSchedule")
      .mockResolvedValue({ ...entry, id: "new-entry" } as ScheduleWriteResponse);
    await copyScheduleEntries([entry], target, pages, []);
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({
        board_id: "secondary",
        page_id: "small",
        recurrence_type: "one_off_date",
        one_off_date: "2026-11-18",
      }),
    );
    expect(create.mock.calls[0][0]).not.toHaveProperty("id");
    expect(create.mock.calls[0][0]).not.toHaveProperty("revision");
  });
  it("refuses incompatible targets before creating any entries", async () => {
    const create = vi.spyOn(api, "createSchedule");
    await expect(copyScheduleEntries([{ ...entry, page_id: "big" }], target, pages, [])).rejects.toThrow(
      "incompatible",
    );
    expect(create).not.toHaveBeenCalled();
  });
  it("rolls back only entries created in this copy if a later creation fails", async () => {
    vi.spyOn(api, "createSchedule")
      .mockResolvedValueOnce({
        ...entry,
        id: "own-new",
        edit_protocol: "schedule-revision-v1",
        revision: "own-new-revision",
      } as ScheduleWriteResponse)
      .mockRejectedValueOnce(new Error("Hub rejected copy"));
    const remove = vi.spyOn(api, "deleteSchedule").mockResolvedValue({ id: "own-new" });
    await expect(copyScheduleEntries([entry, { ...entry, id: "source-two" }], target, pages, [])).rejects.toThrow(
      "Hub rejected copy",
    );
    expect(remove).toHaveBeenCalledExactlyOnceWith("own-new", "own-new-revision");
  });
});

it("reports only its new IDs if rollback is blocked by a concurrent edit or hub failure", async () => {
  vi.spyOn(api, "createSchedule")
    .mockResolvedValueOnce({
      ...entry,
      id: "own-new",
      edit_protocol: "schedule-revision-v1",
      revision: "own-revision",
    } as ScheduleWriteResponse)
    .mockRejectedValueOnce(new Error("Copy failed"));
  vi.spyOn(api, "deleteSchedule").mockRejectedValue(new Error("Revision changed"));
  await expect(copyScheduleEntries([entry, { ...entry, id: "source-two" }], target, pages, [])).rejects.toMatchObject({
    remainingIds: ["own-new"],
  });
});
