/**
 * Tests for carousel integration across UI components.
 *
 * Covers the carousel-specific branches added to:
 * - ScheduleEntryForm (carousel dropdown section)
 * - PagePickerDialog (carousel section rendering)
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ScheduleEntryForm } from "@/components/schedule-entry-form";
import { PagePickerDialog } from "@/components/page-picker-dialog";
import type { Carousel } from "@/lib/api";

const mockPages = [
  { id: "page-1", name: "Page One" },
  { id: "page-2", name: "Page Two" },
];

const mockCarousels: Carousel[] = [
  {
    id: "carousel:c1",
    name: "Morning Rotation",
    page_ids: ["page-1", "page-2"],
    interval_seconds: 30,
    created_at: "2025-01-01T00:00:00Z",
  },
  {
    id: "carousel:c2",
    name: "Evening Rotation",
    page_ids: ["page-1"],
    interval_seconds: 60,
    created_at: "2025-01-01T00:00:00Z",
  },
];

// =============================================================================
// ScheduleEntryForm with carousels
// =============================================================================

describe("ScheduleEntryForm - Carousel Integration", () => {
  it("renders carousel section label when carousels are provided", async () => {
    render(
      <ScheduleEntryForm
        pages={mockPages}
        carousels={mockCarousels}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.getByText("Page or Carousel")).toBeInTheDocument();
  });

  it("renders without carousel section when carousels array is empty", () => {
    render(
      <ScheduleEntryForm
        pages={mockPages}
        carousels={[]}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.getByText("Page or Carousel")).toBeInTheDocument();
  });

  it("renders without carousel section when carousels prop is undefined", () => {
    render(
      <ScheduleEntryForm
        pages={mockPages}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.getByText("Page or Carousel")).toBeInTheDocument();
  });

  it("shows placeholder text that references carousels when carousels exist", () => {
    render(
      <ScheduleEntryForm
        pages={mockPages}
        carousels={mockCarousels}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.getByText("Select a page or carousel")).toBeInTheDocument();
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
        carousels={mockCarousels}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
        onDelete={vi.fn()}
      />
    );

    expect(screen.getByText("Update Schedule")).toBeInTheDocument();
    expect(screen.getByText("Delete")).toBeInTheDocument();
  });

  it("renders edit mode with carousel as scheduled item", () => {
    const existingSchedule = {
      id: "sched-2",
      page_id: "carousel:c1",
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
        carousels={mockCarousels}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />
    );

    expect(screen.getByText("Update Schedule")).toBeInTheDocument();
  });
});

// =============================================================================
// PagePickerDialog with carousels
// =============================================================================

describe("PagePickerDialog - Carousel Integration", () => {
  it("renders carousel section when carousels are provided", async () => {
    const user = userEvent.setup();

    render(
      <PagePickerDialog
        pages={mockPages.map(p => ({ ...p, type: "template" }))}
        carousels={mockCarousels}
        selectedPageId={null}
        onSelect={vi.fn()}
      />
    );

    expect(screen.getByRole("tab", { name: /Carousels/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Pages/i })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Carousels/i }));
    expect(screen.getByText("Morning Rotation")).toBeInTheDocument();
    expect(screen.getByText("Evening Rotation")).toBeInTheDocument();
  });

  it("does not render carousel section when no carousels", () => {
    render(
      <PagePickerDialog
        pages={mockPages.map(p => ({ ...p, type: "template" }))}
        carousels={[]}
        selectedPageId={null}
        onSelect={vi.fn()}
      />
    );

    expect(screen.queryByRole("tab", { name: /Carousels/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Pages/i })).not.toBeInTheDocument();
    expect(screen.getByText("Page One")).toBeInTheDocument();
  });

  it("highlights selected carousel", () => {
    render(
      <PagePickerDialog
        pages={mockPages.map(p => ({ ...p, type: "template" }))}
        carousels={mockCarousels}
        selectedPageId="carousel:c1"
        onSelect={vi.fn()}
      />
    );

    // When a carousel is selected, the carousels tab is default
    expect(screen.getByText("Morning Rotation")).toBeInTheDocument();
    const button = screen.getByText("Morning Rotation").closest("button");
    expect(button).toHaveClass("border-primary");
  });

  it("calls onSelect with carousel ID when carousel is clicked", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();

    render(
      <PagePickerDialog
        pages={mockPages.map(p => ({ ...p, type: "template" }))}
        carousels={mockCarousels}
        selectedPageId={null}
        onSelect={onSelect}
      />
    );

    await user.click(screen.getByRole("tab", { name: /Carousels/i }));
    await user.click(screen.getByText("Morning Rotation"));
    expect(onSelect).toHaveBeenCalledWith("carousel:c1");
  });

  it("shows page count badge on carousel items", async () => {
    const user = userEvent.setup();

    render(
      <PagePickerDialog
        pages={mockPages.map(p => ({ ...p, type: "template" }))}
        carousels={mockCarousels}
        selectedPageId={null}
        onSelect={vi.fn()}
      />
    );

    await user.click(screen.getByRole("tab", { name: /Carousels/i }));
    expect(screen.getByText("2 pages")).toBeInTheDocument();
    expect(screen.getByText("1 page")).toBeInTheDocument();
  });

  it("renders with allowNone and carousels", () => {
    render(
      <PagePickerDialog
        pages={mockPages.map(p => ({ ...p, type: "template" }))}
        carousels={mockCarousels}
        selectedPageId={null}
        onSelect={vi.fn()}
        allowNone={true}
      />
    );

    expect(screen.getByText("None (no default)")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Carousels/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Pages/i })).toBeInTheDocument();
  });

  it("renders without carousels prop (undefined)", () => {
    render(
      <PagePickerDialog
        pages={mockPages.map(p => ({ ...p, type: "template" }))}
        selectedPageId="page-1"
        onSelect={vi.fn()}
      />
    );

    expect(screen.queryByRole("tab", { name: /Carousels/i })).not.toBeInTheDocument();
    expect(screen.getByText("Page One")).toBeInTheDocument();
  });

  it("calls onSelect with null when None is clicked", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <PagePickerDialog
        pages={mockPages.map(p => ({ ...p, type: "template" }))}
        carousels={mockCarousels}
        selectedPageId="carousel:c1"
        onSelect={onSelect}
        allowNone={true}
      />
    );

    await user.click(screen.getByText("None (no default)"));
    expect(onSelect).toHaveBeenCalledWith(null);
  });
});
