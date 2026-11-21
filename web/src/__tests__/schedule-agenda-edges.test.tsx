/** BB-C-3 / BB-C-6: the Day agenda marks the current gap and reads whole days and overnight entries. */
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";

import { ScheduleAgenda } from "@/components/schedule/schedule-agenda";
import type { Page, ScheduleEntry } from "@/lib/api";

const pages = [
  { id: "late", name: "Grocery List" },
  { id: "day", name: "Clock & Date" },
] as Page[];
const monday = new Date(2026, 10, 16);
const overnight = {
  id: "overnight",
  page_id: "late",
  start_time: "23:30",
  end_time: "02:00",
  enabled: true,
  day_pattern: "all",
} as ScheduleEntry;

it("labels both halves of an overnight entry with its whole range", () => {
  render(<ScheduleAgenda date={monday} schedules={[overnight]} pages={pages} onEdit={vi.fn()} />);
  const rows = screen.getAllByRole("button", { name: /Grocery List/ });
  expect(rows).toHaveLength(2);
  for (const row of rows) expect(row).toHaveTextContent("11:30 PM – 2:00 AM");
  expect(screen.queryByText(/11:59 PM/)).not.toBeInTheDocument();
});

it("ends the day's last gap and an open-ended entry at 12:00 AM", () => {
  const open = { ...overnight, id: "open", page_id: "day", start_time: "20:00", end_time: null };
  render(
    <ScheduleAgenda
      date={monday}
      schedules={[open]}
      pages={pages}
      gaps={[
        { start_time: "00:00", end_time: "20:00", days: ["monday"] },
        { start_time: "23:00", end_time: "23:59", days: ["tuesday"] },
      ]}
      onEdit={vi.fn()}
    />,
  );
  expect(screen.getByRole("button", { name: /Clock & Date/ })).toHaveTextContent("8:00 PM – 12:00 AM");
  render(
    <ScheduleAgenda
      date={new Date(2026, 10, 17)}
      schedules={[]}
      pages={pages}
      gaps={[{ start_time: "23:00", end_time: "23:59", days: ["tuesday"] }]}
      onEdit={vi.fn()}
    />,
  );
  expect(screen.getByText(/11:00 PM – 12:00 AM/)).toBeInTheDocument();
  expect(screen.queryByText(/11:59 PM/)).not.toBeInTheDocument();
});

it("marks the gap the board is in right now as Now", () => {
  render(
    <ScheduleAgenda
      date={monday}
      now={new Date(2026, 10, 16, 0, 57)}
      schedules={[{ ...overnight, start_time: "06:00", end_time: "23:00", page_id: "day", id: "d" }]}
      pages={pages}
      gaps={[
        { start_time: "00:00", end_time: "06:00", days: ["monday"] },
        { start_time: "23:00", end_time: "23:59", days: ["monday"] },
      ]}
      onEdit={vi.fn()}
    />,
  );
  const current = screen.getAllByText("Now");
  expect(current).toHaveLength(1);
  expect(current[0].closest('[aria-current="time"]')).toHaveTextContent("12:00 AM – 6:00 AM");
});

it("does not mark a gap on another day as Now", () => {
  render(
    <ScheduleAgenda
      date={new Date(2026, 10, 17)}
      now={new Date(2026, 10, 16, 0, 57)}
      schedules={[]}
      pages={pages}
      gaps={[{ start_time: "00:00", end_time: "23:59", days: ["tuesday"] }]}
      onEdit={vi.fn()}
    />,
  );
  expect(screen.queryByText("Now")).not.toBeInTheDocument();
});
