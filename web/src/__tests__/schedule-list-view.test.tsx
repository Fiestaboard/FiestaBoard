/**
 * Tests for ScheduleListView component.
 *
 * Validates:
 *  1. Day formatting (all, weekdays, weekends, custom patterns)
 *  2. Custom day abbreviation lookup is case-insensitive and robust
 *  3. Aria-labels on Edit/Delete buttons include the page name for accessibility
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ScheduleListView } from "@/app/schedule/components/schedule-list-view";
import type { Page, ScheduleEntry } from "@/lib/api";

const MOCK_PAGES: Page[] = [
  {
    id: "page-1",
    name: "Morning Board",
    type: "template",
    device_type: "flagship",
    duration_seconds: 30,
    created_at: "2025-01-01T00:00:00Z",
  },
];

function makeSchedule(overrides: Partial<ScheduleEntry>): ScheduleEntry {
  return {
    id: "sched-1",
    page_id: "page-1",
    start_time: "09:00",
    end_time: "17:00",
    day_pattern: "all",
    enabled: true,
    created_at: "2025-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("ScheduleListView – formatDays", () => {
  it("shows 'All days' for day_pattern='all'", () => {
    render(
      <ScheduleListView
        schedules={[makeSchedule({ day_pattern: "all" })]}
        pages={MOCK_PAGES}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/All days/)).toBeInTheDocument();
  });

  it("shows 'Mon-Fri' for day_pattern='weekdays'", () => {
    render(
      <ScheduleListView
        schedules={[makeSchedule({ day_pattern: "weekdays" })]}
        pages={MOCK_PAGES}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/Mon-Fri/)).toBeInTheDocument();
  });

  it("shows 'Sat-Sun' for day_pattern='weekends'", () => {
    render(
      <ScheduleListView
        schedules={[makeSchedule({ day_pattern: "weekends" })]}
        pages={MOCK_PAGES}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/Sat-Sun/)).toBeInTheDocument();
  });

  it("formats custom days using full lowercase names", () => {
    render(
      <ScheduleListView
        schedules={[
          makeSchedule({
            day_pattern: "custom",
            custom_days: ["monday", "wednesday", "friday"],
          }),
        ]}
        pages={MOCK_PAGES}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/Mon, Wed, Fri/)).toBeInTheDocument();
  });

  it("formats custom days using 3-letter lowercase abbreviations", () => {
    render(
      <ScheduleListView
        schedules={[
          makeSchedule({
            day_pattern: "custom",
            custom_days: ["mon", "wed", "fri"],
          }),
        ]}
        pages={MOCK_PAGES}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/Mon, Wed, Fri/)).toBeInTheDocument();
  });

  it("is case-insensitive for custom day names (uppercase input)", () => {
    render(
      <ScheduleListView
        schedules={[
          makeSchedule({
            day_pattern: "custom",
            custom_days: ["MONDAY", "SATURDAY"],
          }),
        ]}
        pages={MOCK_PAGES}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/Mon, Sat/)).toBeInTheDocument();
  });

  it("is case-insensitive for custom day names (mixed-case input)", () => {
    render(
      <ScheduleListView
        schedules={[
          makeSchedule({
            day_pattern: "custom",
            custom_days: ["Tuesday", "Sunday"],
          }),
        ]}
        pages={MOCK_PAGES}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    expect(screen.getByText(/Tue, Sun/)).toBeInTheDocument();
  });

  it("falls back to the trimmed original value for unknown day names", () => {
    render(
      <ScheduleListView
        schedules={[
          makeSchedule({
            day_pattern: "custom",
            custom_days: ["holiday", "  monday  "],
          }),
        ]}
        pages={MOCK_PAGES}
        onEdit={vi.fn()}
        onDelete={vi.fn()}
      />,
    );
    // "holiday" is unknown → kept as-is; "  monday  " → trimmed to "monday" → "Mon"
    expect(screen.getByText(/holiday, Mon/)).toBeInTheDocument();
  });
});

describe("ScheduleListView – accessibility aria-labels", () => {
  it("Edit button has aria-label including the page name", () => {
    render(<ScheduleListView schedules={[makeSchedule({})]} pages={MOCK_PAGES} onEdit={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Edit schedule for Morning Board" })).toBeInTheDocument();
  });

  it("Delete button has aria-label including the page name", () => {
    render(<ScheduleListView schedules={[makeSchedule({})]} pages={MOCK_PAGES} onEdit={vi.fn()} onDelete={vi.fn()} />);
    expect(screen.getByRole("button", { name: "Delete schedule for Morning Board" })).toBeInTheDocument();
  });

  it("Edit and Delete buttons call their handlers with correct arguments", () => {
    const onEdit = vi.fn();
    const onDelete = vi.fn();
    const schedule = makeSchedule({});

    render(<ScheduleListView schedules={[schedule]} pages={MOCK_PAGES} onEdit={onEdit} onDelete={onDelete} />);

    screen.getByRole("button", { name: "Edit schedule for Morning Board" }).click();
    expect(onEdit).toHaveBeenCalledWith(schedule);

    screen.getByRole("button", { name: "Delete schedule for Morning Board" }).click();
    expect(onDelete).toHaveBeenCalledWith("sched-1");
  });
});
