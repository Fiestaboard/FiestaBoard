import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { defaultScheduleView, ScheduleAgenda } from "@/components/schedule/schedule-agenda";
import type { Page, ScheduleEntry } from "@/lib/api";
const pages = [
  { id: "morning", name: "Morning page" },
  { id: "fallback", name: "Fallback page" },
] as Page[];
const entry = {
  id: "weekly",
  page_id: "morning",
  start_time: "09:00",
  end_time: "12:00",
  enabled: true,
  day_pattern: "weekdays",
} as ScheduleEntry;
describe("Schedule agenda", () => {
  it("defaults to Day on phones, List on tablets, and Week on desktops", () => {
    expect(defaultScheduleView(390)).toBe("day");
    expect(defaultScheduleView(900)).toBe("list");
    expect(defaultScheduleView(1280)).toBe("calendar");
  });
  it("shows only occurrences on the chosen day and opens the original entry", () => {
    const edit = vi.fn();
    render(<ScheduleAgenda date={new Date(2026, 10, 16)} schedules={[entry]} pages={pages} onEdit={edit} />);
    fireEvent.click(screen.getByRole("button", { name: /Morning page/ }));
    expect(edit).toHaveBeenCalledWith(entry);
  });
  it("does not show a weekday entry on Sunday", () => {
    render(<ScheduleAgenda date={new Date(2026, 10, 15)} schedules={[entry]} pages={pages} onEdit={vi.fn()} />);
    expect(screen.queryByText("Morning page")).not.toBeInTheDocument();
    expect(screen.getByText("No entries on this day")).toBeInTheDocument();
  });
  it("uses the existing recurrence transformer for date-specific entries", () => {
    const once = {
      ...entry,
      recurrence_type: "one_off_date",
      one_off_date: "2026-11-17",
      day_pattern: "all",
    } as ScheduleEntry;
    render(<ScheduleAgenda date={new Date(2026, 10, 16)} schedules={[once]} pages={pages} onEdit={vi.fn()} />);
    expect(screen.queryByText("Morning page")).not.toBeInTheDocument();
  });
});

it("interleaves hub gaps between entries in chronological reading order", () => {
  const evening = { ...entry, id: "evening", page_id: "fallback", start_time: "18:00", end_time: "21:00" };
  render(
    <ScheduleAgenda
      date={new Date(2026, 10, 16)}
      schedules={[evening, entry]}
      pages={pages}
      defaultPageId="fallback"
      gaps={[{ start_time: "12:00", end_time: "18:00", days: ["monday"] }]}
      onEdit={vi.fn()}
    />,
  );
  const rows = screen.getAllByRole("listitem");
  expect(rows[0]).toHaveTextContent("Morning page");
  expect(rows[1]).toHaveTextContent("Gap · Fallback page");
  expect(rows[2]).toHaveTextContent("Fallback page");
});
