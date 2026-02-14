/**
 * Tests for schedule entry form validation - midnight rollover support.
 *
 * These tests verify that the frontend form validation:
 * 1. Allows midnight rollover schedules (e.g., 23:00-03:00)
 * 2. Allows schedules ending at midnight (e.g., 23:00-00:00)
 * 3. Still prevents zero-duration schedules (e.g., 12:00-12:00)
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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
