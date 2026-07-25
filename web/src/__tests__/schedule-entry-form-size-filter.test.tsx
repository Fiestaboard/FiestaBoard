/**
 * Tests for page<->board size filtering in ScheduleEntryForm (issue #1249).
 *
 * The form should only offer pages whose size matches the current board
 * (from useCurrentBoard), keep the already-selected page visible when
 * editing, and surface a non-fatal warning when a selected collection only
 * partially fits the board. With no current board (single-board installs
 * before boards load, and all existing tests) the behavior is unchanged.
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ScheduleEntryForm } from "@/components/schedule-entry-form";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
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
  it("only offers pages compatible with the current board", async () => {
    const user = userEvent.setup();
    renderInSheet({ pages: PAGES, onSubmit: vi.fn(), onCancel: vi.fn() });

    await user.click(screen.getByLabelText("Page or Collection"));
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());

    expect(screen.getByRole("option", { name: /Flagship Page/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Note Page/ })).not.toBeInTheDocument();
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

  it("keeps the selected page visible when editing an incompatible entry", async () => {
    const user = userEvent.setup();
    renderInSheet({
      pages: PAGES,
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
      prefillPageId: "page-note",
    });

    // The incompatible-but-selected page stays selectable and a warning shows.
    expect(screen.getByLabelText("Page or Collection")).toHaveTextContent("Note Page");
    expect(screen.getByText(/doesn't match this board's size/)).toBeInTheDocument();

    await user.click(screen.getByLabelText("Page or Collection"));
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    expect(screen.getByRole("option", { name: /Note Page/ })).toBeInTheDocument();
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
