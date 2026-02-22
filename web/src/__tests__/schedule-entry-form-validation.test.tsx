/**
 * Tests for schedule entry form validation and delete button behavior.
 *
 * These tests verify that the frontend form validation:
 * 1. Allows midnight rollover schedules (e.g., 23:00-03:00)
 * 2. Allows schedules ending at midnight (e.g., 23:00-00:00)
 * 3. Still prevents zero-duration schedules (e.g., 12:00-12:00)
 * 4. Shows delete button only when editing with onDelete provided
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ScheduleEntryForm } from "@/components/schedule-entry-form";

// Mock pages for the form
const mockPages = [
  { id: "page-1", name: "Night Dashboard" },
  { id: "page-2", name: "Morning Dashboard" },
];

describe("ScheduleEntryForm - Midnight Rollover Validation", () => {
  it("should NOT show validation error for midnight rollover (23:00-03:00)", async () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      <ScheduleEntryForm
        pages={mockPages}
        onSubmit={onSubmit}
        onCancel={onCancel}
        prefillStartTime="23:00"
        prefillEndTime="03:00"
        prefillDayPattern="all"
      />
    );

    // Wait for validation to run
    await waitFor(() => {
      // The form should NOT show "End time must be after start time" error
      const errorText = screen.queryByText("End time must be after start time");
      expect(errorText).not.toBeInTheDocument();
    });
  });

  it("should NOT show validation error for schedule ending at midnight (23:00-00:00)", async () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      <ScheduleEntryForm
        pages={mockPages}
        onSubmit={onSubmit}
        onCancel={onCancel}
        prefillStartTime="23:00"
        prefillEndTime="00:00"
        prefillDayPattern="all"
      />
    );

    await waitFor(() => {
      const errorText = screen.queryByText("End time must be after start time");
      expect(errorText).not.toBeInTheDocument();
    });
  });

  it("should still show validation error for zero-duration schedule (12:00-12:00)", async () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      <ScheduleEntryForm
        pages={mockPages}
        onSubmit={onSubmit}
        onCancel={onCancel}
        prefillStartTime="12:00"
        prefillEndTime="12:00"
        prefillDayPattern="all"
      />
    );

    await waitFor(() => {
      const errorText = screen.queryByText(/End time must be different from start time/);
      expect(errorText).toBeInTheDocument();
    });
  });

  it("should NOT show validation error for normal schedule (09:00-17:00)", async () => {
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    render(
      <ScheduleEntryForm
        pages={mockPages}
        onSubmit={onSubmit}
        onCancel={onCancel}
        prefillStartTime="09:00"
        prefillEndTime="17:00"
        prefillDayPattern="all"
      />
    );

    await waitFor(() => {
      const errorText = screen.queryByText("End time must be after start time");
      expect(errorText).not.toBeInTheDocument();
    });
  });
});

const mockSchedule = {
  id: "sched-1",
  page_id: "page-1",
  start_time: "09:00",
  end_time: "17:00",
  day_pattern: "all" as const,
  custom_days: [],
  enabled: true,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-01-01T00:00:00Z",
};

describe("ScheduleEntryForm - Delete Button", () => {
  it("should show delete button when editing with onDelete provided", () => {
    render(
      <ScheduleEntryForm
        schedule={mockSchedule}
        pages={mockPages}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByRole("button", { name: /delete/i })).toBeInTheDocument();
  });

  it("should NOT show delete button when creating a new schedule", () => {
    render(
      <ScheduleEntryForm
        pages={mockPages}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
  });

  it("should NOT show delete button when onDelete is not provided", () => {
    render(
      <ScheduleEntryForm
        schedule={mockSchedule}
        pages={mockPages}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.queryByRole("button", { name: /delete/i })).not.toBeInTheDocument();
  });

  it("should call onDelete when delete button is clicked", async () => {
    const onDelete = vi.fn();

    render(
      <ScheduleEntryForm
        schedule={mockSchedule}
        pages={mockPages}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        onDelete={onDelete}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /delete/i }));
    expect(onDelete).toHaveBeenCalledTimes(1);
  });
});
