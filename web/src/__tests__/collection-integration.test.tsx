/**
 * Tests for collection integration across UI components.
 *
 * Covers the collection-specific branches added to:
 * - ScheduleEntryForm (collection dropdown section)
 * - PagePickerDialog (collection section rendering)
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { PagePickerDialog } from "@/components/page-picker-dialog";
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

// =============================================================================
// PagePickerDialog with collections
// =============================================================================

describe("PagePickerDialog - Collection Integration", () => {
  it("renders collection section when collections are provided", async () => {
    const user = userEvent.setup();

    render(
      <PagePickerDialog
        pages={mockPages.map((p) => ({ ...p, type: "template" }))}
        collections={mockCollections}
        selectedPageId={null}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByRole("tab", { name: /Collections/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Pages/i })).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Collections/i }));
    expect(screen.getByText("Morning Rotation")).toBeInTheDocument();
    expect(screen.getByText("Evening Rotation")).toBeInTheDocument();
  });

  it("does not render collection section when no collections", () => {
    render(
      <PagePickerDialog
        pages={mockPages.map((p) => ({ ...p, type: "template" }))}
        collections={[]}
        selectedPageId={null}
        onSelect={vi.fn()}
      />,
    );

    expect(screen.queryByRole("tab", { name: /Collections/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Pages/i })).not.toBeInTheDocument();
    expect(screen.getByText("Page One")).toBeInTheDocument();
  });

  it("highlights selected collection", () => {
    render(
      <PagePickerDialog
        pages={mockPages.map((p) => ({ ...p, type: "template" }))}
        collections={mockCollections}
        selectedPageId="collection:c1"
        onSelect={vi.fn()}
      />,
    );

    // When a collection is selected, the collections tab is default
    expect(screen.getByText("Morning Rotation")).toBeInTheDocument();
    const button = screen.getByText("Morning Rotation").closest("button");
    expect(button).toHaveClass("border-brand");
  });

  it("calls onSelect with collection ID when collection is clicked", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();

    render(
      <PagePickerDialog
        pages={mockPages.map((p) => ({ ...p, type: "template" }))}
        collections={mockCollections}
        selectedPageId={null}
        onSelect={onSelect}
      />,
    );

    await user.click(screen.getByRole("tab", { name: /Collections/i }));
    await user.click(screen.getByText("Morning Rotation"));
    expect(onSelect).toHaveBeenCalledWith("collection:c1");
  });

  it("shows page count badge on collection items", async () => {
    const user = userEvent.setup();

    render(
      <PagePickerDialog
        pages={mockPages.map((p) => ({ ...p, type: "template" }))}
        collections={mockCollections}
        selectedPageId={null}
        onSelect={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("tab", { name: /Collections/i }));
    expect(screen.getByText("2 pages")).toBeInTheDocument();
    expect(screen.getByText("1 page")).toBeInTheDocument();
  });

  it("renders with allowNone and collections", () => {
    render(
      <PagePickerDialog
        pages={mockPages.map((p) => ({ ...p, type: "template" }))}
        collections={mockCollections}
        selectedPageId={null}
        onSelect={vi.fn()}
        allowNone={true}
      />,
    );

    expect(screen.getByText("None (no default)")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Collections/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /Pages/i })).toBeInTheDocument();
  });

  it("renders without collections prop (undefined)", () => {
    render(
      <PagePickerDialog
        pages={mockPages.map((p) => ({ ...p, type: "template" }))}
        selectedPageId="page-1"
        onSelect={vi.fn()}
      />,
    );

    expect(screen.queryByRole("tab", { name: /Collections/i })).not.toBeInTheDocument();
    expect(screen.getByText("Page One")).toBeInTheDocument();
  });

  it("calls onSelect with null when None is clicked", async () => {
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(
      <PagePickerDialog
        pages={mockPages.map((p) => ({ ...p, type: "template" }))}
        collections={mockCollections}
        selectedPageId="collection:c1"
        onSelect={onSelect}
        allowNone={true}
      />,
    );

    await user.click(screen.getByText("None (no default)"));
    expect(onSelect).toHaveBeenCalledWith(null);
  });
});
