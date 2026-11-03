/**
 * Tests for page<->board size filtering in ScheduleEntryForm (issue #1249).
 *
 * The form offers every page, but a page the current board (from
 * useCurrentBoard) can't show is a disabled option carrying its reason
 * ("Made for a 3×15 board"), so it is flagged rather than hidden. The
 * already-selected page stays selectable when editing, and the form surfaces
 * a non-fatal warning when the selection only partially fits the board. With
 * no current board (single-board installs before boards load, and all
 * existing tests) the behavior is unchanged.
 */

import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@fiestaboard/ui";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ScheduleEntryForm } from "@/components/schedule-entry-form";
import type { Collection } from "@/lib/api";

const mockUseCurrentBoard = vi.fn();

vi.mock("@/components/current-board-context", () => ({
  useCurrentBoard: () => mockUseCurrentBoard(),
}));

const FLAGSHIP_BOARD = {
  id: "board-1",
  name: "Big Board",
  device_type: "flagship",
  notes_wide: 1,
  notes_tall: 1,
};

const PAGES = [
  { id: "page-flag", name: "Flagship Page", device_type: "flagship" },
  { id: "page-note", name: "Note Page", device_type: "note" },
];

// An 8x10 Pixoo in its 5x7 text size, which can also draw a 10x16 grid in 3x5.
const PIXOO_BOARD = {
  id: "board-pixoo",
  name: "Pixoo",
  device_type: "panel",
  grid_rows: 8,
  grid_cols: 10,
  producible_grids: { "5x7": [8, 10], "3x5": [10, 16] },
  led_layout: { font: "5x7" },
};

const PIXOO_PAGES = [
  { id: "page-small-text", name: "Small Text Page", device_type: "panel", grid_rows: 10, grid_cols: 16 },
];

const MIXED_COLLECTION = {
  id: "collection:mixed",
  name: "Mixed Sizes",
  page_ids: ["page-flag", "page-note"],
  selection_mode: "time",
} as unknown as Collection;

function renderInSheet(props: Parameters<typeof ScheduleEntryForm>[0]) {
  return render(
    <Sheet open={true}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Add Schedule</SheetTitle>
          <SheetDescription>Configure schedule entry</SheetDescription>
        </SheetHeader>
        <ScheduleEntryForm {...props} />
      </SheetContent>
    </Sheet>,
  );
}

beforeEach(() => {
  mockUseCurrentBoard.mockReturnValue({
    currentBoardId: FLAGSHIP_BOARD.id,
    currentBoard: FLAGSHIP_BOARD,
    boards: [FLAGSHIP_BOARD],
    setCurrentBoardId: vi.fn(),
  });
});

describe("ScheduleEntryForm size filtering", () => {
  it("offers a page that doesn't fit as a disabled option with its reason", async () => {
    const user = userEvent.setup();
    renderInSheet({ pages: PAGES, onSubmit: vi.fn(), onCancel: vi.fn() });

    await user.click(screen.getByLabelText("Page or Collection"));
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());

    const option = screen.getByRole("option", { name: /Note Page/ });
    expect(option).toHaveAttribute("aria-disabled", "true");
    expect(option).toHaveTextContent("Made for a 3×15 board");
  });

  it("offers a page that fits as an enabled option without a reason", async () => {
    const user = userEvent.setup();
    renderInSheet({ pages: PAGES, onSubmit: vi.fn(), onCancel: vi.fn() });

    await user.click(screen.getByLabelText("Page or Collection"));
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());

    const option = screen.getByRole("option", { name: /Flagship Page/ });
    expect(option).not.toHaveAttribute("aria-disabled", "true");
    expect(option).not.toHaveTextContent("Made for a");
  });

  it("offers a 10x16 page to an 8x10 Pixoo as selectable", async () => {
    mockUseCurrentBoard.mockReturnValue({
      currentBoardId: PIXOO_BOARD.id,
      currentBoard: PIXOO_BOARD,
      boards: [PIXOO_BOARD],
      setCurrentBoardId: vi.fn(),
    });
    const user = userEvent.setup();
    renderInSheet({ pages: PIXOO_PAGES, onSubmit: vi.fn(), onCancel: vi.fn() });

    await user.click(screen.getByLabelText("Page or Collection"));
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());

    const option = screen.getByRole("option", { name: /Small Text Page/ });
    expect(option).not.toHaveAttribute("aria-disabled", "true");
    expect(option).not.toHaveTextContent("Made for a");
  });

  it("shows all pages when no current board is resolved (unchanged behavior)", async () => {
    mockUseCurrentBoard.mockReturnValue({
      currentBoardId: "",
      currentBoard: undefined,
      boards: [],
      setCurrentBoardId: vi.fn(),
    });
    const user = userEvent.setup();
    renderInSheet({ pages: PAGES, onSubmit: vi.fn(), onCancel: vi.fn() });

    await user.click(screen.getByLabelText("Page or Collection"));
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());

    expect(screen.getByRole("option", { name: /Flagship Page/ })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: /Note Page/ })).toBeInTheDocument();
  });

  it("warns with the reason when editing an entry whose page no longer fits", () => {
    renderInSheet({
      pages: PAGES,
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
      prefillPageId: "page-note",
    });

    expect(screen.getByLabelText("Page or Collection")).toHaveTextContent("Note Page");
    const warning = screen.getByText(/doesn't match this board's size/);
    expect(warning).toHaveTextContent("Made for a 3×15 board");
  });

  it("keeps the selected misfit page selectable when editing", async () => {
    const user = userEvent.setup();
    renderInSheet({
      pages: PAGES,
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
      prefillPageId: "page-note",
    });

    await user.click(screen.getByLabelText("Page or Collection"));
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    expect(screen.getByRole("option", { name: /Note Page/ })).not.toHaveAttribute("aria-disabled", "true");
  });

  it("warns when a selected collection only partially fits the board", () => {
    renderInSheet({
      pages: PAGES,
      collections: [MIXED_COLLECTION],
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
      prefillPageId: MIXED_COLLECTION.id,
    });

    expect(screen.getByText(/1 of 2 pages in this collection don't fit/)).toBeInTheDocument();
  });

  it("does not warn for a fully compatible selection", () => {
    renderInSheet({
      pages: PAGES,
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
      prefillPageId: "page-flag",
    });

    expect(screen.queryByText(/doesn't match this board's size/)).not.toBeInTheDocument();
    expect(screen.queryByText(/will be skipped/)).not.toBeInTheDocument();
  });
});
