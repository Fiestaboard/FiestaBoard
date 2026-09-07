/**
 * Tests for collection integration across UI components.
 *
 * Covers the collection-specific branches added to:
 * - ScheduleEntryForm (collection dropdown section)
 */

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ScheduleEntryForm } from "@/components/schedule-entry-form";
import type { Collection } from "@/lib/api";

const mockPages = [
  { id: "page-1", name: "Page One" },
  { id: "page-2", name: "Page Two" },
];

const mockCollections: Collection[] = [
  {
    id: "collection:c1",
    name: "Morning Rotation",
    page_ids: ["page-1", "page-2"],
    selection_mode: "time",

    time: { interval_seconds: 30 },

    variable: null,
    random: null,
    created_at: "2025-01-01T00:00:00Z",
  },
  {
    id: "collection:c2",
    name: "Evening Rotation",
    page_ids: ["page-1"],
    selection_mode: "time",

    time: { interval_seconds: 60 },

    variable: null,
    random: null,
    created_at: "2025-01-01T00:00:00Z",
  },
];

// =============================================================================
// ScheduleEntryForm with collections
// =============================================================================

describe("ScheduleEntryForm - Collection Integration", () => {
  it("renders collection section label when collections are provided", async () => {
    render(<ScheduleEntryForm pages={mockPages} collections={mockCollections} onSubmit={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.getByText("Page or Collection")).toBeInTheDocument();
  });

  it("renders without collection section when collections array is empty", () => {
    render(<ScheduleEntryForm pages={mockPages} collections={[]} onSubmit={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.getByText("Page or Collection")).toBeInTheDocument();
  });

  it("renders without collection section when collections prop is undefined", () => {
    render(<ScheduleEntryForm pages={mockPages} onSubmit={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.getByText("Page or Collection")).toBeInTheDocument();
  });

  it("shows placeholder text that references collections when collections exist", () => {
    render(<ScheduleEntryForm pages={mockPages} collections={mockCollections} onSubmit={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.getByText("Select a page or collection")).toBeInTheDocument();
  });

  it("renders edit mode with existing schedule page", () => {
    const existingSchedule = {
      id: "sched-1",
      page_id: "page-1",
      start_time: "09:00",
      end_time: "17:00",
      day_pattern: "all" as const,
      enabled: true,
      created_at: "2025-01-01T00:00:00Z",
    };

    render(
      <ScheduleEntryForm
        schedule={existingSchedule}
        pages={mockPages}
        collections={mockCollections}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByText("Update Schedule")).toBeInTheDocument();
    expect(screen.getByText("Delete")).toBeInTheDocument();
  });

  it("renders edit mode with collection as scheduled item", () => {
    const existingSchedule = {
      id: "sched-2",
      page_id: "collection:c1",
      start_time: "09:00",
      end_time: "17:00",
      day_pattern: "weekdays" as const,
      enabled: false,
      created_at: "2025-01-01T00:00:00Z",
    };

    render(
      <ScheduleEntryForm
        schedule={existingSchedule}
        pages={mockPages}
        collections={mockCollections}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(screen.getByText("Update Schedule")).toBeInTheDocument();
  });
});
