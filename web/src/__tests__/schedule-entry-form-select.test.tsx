/**
 * Tests for Select dropdown interactions (mouse and keyboard) inside a Sheet.
 *
 * Root cause of the original bug: Radix UI Dialog (Sheet) sets
 * `document.body.style.pointerEvents = "none"` in modal mode. Radix Select
 * portals its content into document.body, which then inherits that rule —
 * so mouse clicks on Select options are silently swallowed. Keyboard events
 * still work because they dispatch directly to the focused element.
 *
 * Fix: `modal={false}` on each Select nested inside a Sheet. The Sheet
 * already handles modal behavior; the Select doesn't need to participate.
 *
 * These tests render ScheduleEntryForm inside an open Sheet to replicate
 * the real usage context and assert that both mouse-click and keyboard
 * interactions work correctly.
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ScheduleEntryForm } from "@/components/schedule-entry-form";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

const mockPages = [
  { id: "page-1", name: "Morning Dashboard" },
  { id: "page-2", name: "Evening Dashboard" },
];

/** Wrap the form in an open Sheet, matching the real schedule page context. */
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
    </Sheet>
  );
}

// ---------------------------------------------------------------------------
// Page / Carousel Select
// ---------------------------------------------------------------------------
describe("ScheduleEntryForm page Select inside Sheet", () => {
  it("mouse-click: clicking a page option selects it", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    renderInSheet({ pages: mockPages, onSubmit, onCancel });

    // Use label association to find the page combobox specifically
    const trigger = screen.getByLabelText("Page or Carousel");
    await user.click(trigger);

    // Wait for the Select listbox to appear
    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeInTheDocument();
    });

    // Click an option with mouse
    const option = screen.getByRole("option", { name: "Morning Dashboard" });
    await user.click(option);

    // The combobox should now display the selected page name
    await waitFor(() => {
      expect(trigger).toHaveTextContent("Morning Dashboard");
    });
  });

  it("keyboard: ArrowDown then Enter selects a page option", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    const onCancel = vi.fn();

    renderInSheet({ pages: mockPages, onSubmit, onCancel });

    const trigger = screen.getByLabelText("Page or Carousel");
    await user.click(trigger);

    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeInTheDocument();
    });

    // Navigate down and confirm
    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");

    await waitFor(() => {
      // Should have selected one of the pages (first highlighted)
      expect(trigger).not.toHaveTextContent(/select page/i);
    });
  });
});

// ---------------------------------------------------------------------------
// Start-time Select
// ---------------------------------------------------------------------------
describe("ScheduleEntryForm start-time Select inside Sheet", () => {
  it("mouse-click: clicking a time option updates start time", async () => {
    const user = userEvent.setup();

    renderInSheet({
      pages: mockPages,
      prefillStartTime: "09:00",
      prefillEndTime: "17:00",
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
    });

    const startTimeTrigger = screen.getByLabelText("Start Time");
    await user.click(startTimeTrigger);

    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeInTheDocument();
    });

    // Click the 10:00 option
    const option = screen.getByRole("option", { name: "10:00" });
    await user.click(option);

    await waitFor(() => {
      expect(startTimeTrigger).toHaveTextContent("10:00");
    });
  }, 40000);

  it("keyboard: ArrowDown then Enter updates start time", async () => {
    const user = userEvent.setup();

    renderInSheet({
      pages: mockPages,
      prefillStartTime: "09:00",
      prefillEndTime: "17:00",
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
    });

    const startTimeTrigger = screen.getByLabelText("Start Time");

    // Open via Space key (Radix Select standard keyboard trigger)
    await user.click(startTimeTrigger);

    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeInTheDocument();
    });

    // Move to next option and select
    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");

    // The trigger should show a different time (next minute after 09:00)
    await waitFor(() => {
      expect(startTimeTrigger).toHaveTextContent("09:01");
    });
  });
});

// ---------------------------------------------------------------------------
// End-time Select
// ---------------------------------------------------------------------------
describe("ScheduleEntryForm end-time Select inside Sheet", () => {
  it("mouse-click: clicking a time option updates end time", async () => {
    const user = userEvent.setup();

    renderInSheet({
      pages: mockPages,
      prefillStartTime: "09:00",
      prefillEndTime: "17:00",
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
    });

    const endTimeTrigger = screen.getByLabelText("End Time");
    await user.click(endTimeTrigger);

    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeInTheDocument();
    });

    // Click the 18:00 option
    const option = screen.getByRole("option", { name: "18:00" });
    await user.click(option);

    await waitFor(() => {
      expect(endTimeTrigger).toHaveTextContent("18:00");
    });
  });

  it("keyboard: ArrowDown then Enter updates end time", async () => {
    const user = userEvent.setup();

    renderInSheet({
      pages: mockPages,
      prefillStartTime: "09:00",
      prefillEndTime: "17:00",
      onSubmit: vi.fn(),
      onCancel: vi.fn(),
    });

    const endTimeTrigger = screen.getByLabelText("End Time");
    await user.click(endTimeTrigger);

    await waitFor(() => {
      expect(screen.getByRole("listbox")).toBeInTheDocument();
    });

    await user.keyboard("{ArrowDown}");
    await user.keyboard("{Enter}");

    await waitFor(() => {
      expect(endTimeTrigger).toHaveTextContent("17:01");
    });
  });
});
