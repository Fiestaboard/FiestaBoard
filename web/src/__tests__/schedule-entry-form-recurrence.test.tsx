/**
 * Tests for the recurrence-type selector inside ScheduleEntryForm:
 *   - weekly (existing default)
 *   - annual_date (MM-DD), optional date range
 *   - one_off_date (YYYY-MM-DD), optional date range
 *
 * Covers rendering, validation, edit prefill, and submit payload shape for
 * the date-override branches added in PR #861.
 */

import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ScheduleEntryForm } from "@/components/schedule-entry-form";
import type { ScheduleEntry } from "@/lib/api";

const mockPages = [
  { id: "page-1", name: "Morning Dashboard" },
  { id: "page-2", name: "Evening Dashboard" },
];

const baseScheduleFields = {
  id: "sch-1",
  page_id: "page-1",
  start_time: "09:00",
  end_time: "17:00",
  day_pattern: "all" as const,
  enabled: true,
  created_at: "2026-01-01T00:00:00Z",
};

async function selectRecurrence(
  user: ReturnType<typeof userEvent.setup>,
  label: "Weekly" | "Annual date" | "Specific date",
) {
  const trigger = screen.getByLabelText("Recurrence");
  await user.click(trigger);
  await waitFor(() => {
    expect(screen.getByRole("listbox")).toBeInTheDocument();
  });
  const option = screen.getByRole("option", { name: label });
  await user.click(option);
  await waitFor(() => {
    expect(trigger).toHaveTextContent(label);
  });
}

describe("ScheduleEntryForm — annual_date recurrence", () => {
  it("renders annual date fields after selecting Annual recurrence", async () => {
    const user = userEvent.setup();
    render(<ScheduleEntryForm pages={mockPages} prefillPageId="page-1" onSubmit={vi.fn()} onCancel={vi.fn()} />);

    await selectRecurrence(user, "Annual date");
    expect(screen.getByText("Date (month / day)")).toBeInTheDocument();
    expect(screen.getByLabelText("Use a date range")).toBeInTheDocument();
    // Day selector (weekly-only) should NOT be in the document anymore
    expect(screen.queryByText(/days of week/i)).not.toBeInTheDocument();
  });

  it("shows validation error when annual month/day not picked", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ScheduleEntryForm pages={mockPages} prefillPageId="page-1" onSubmit={onSubmit} onCancel={vi.fn()} />);

    await selectRecurrence(user, "Annual date");
    await waitFor(() => {
      expect(screen.getByText("Please pick a month and day")).toBeInTheDocument();
    });
    // Submit button disabled by validation
    const submit = screen.getByRole("button", { name: /create|update/i });
    expect(submit).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits annual_date payload with single date", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ScheduleEntryForm pages={mockPages} prefillPageId="page-1" onSubmit={onSubmit} onCancel={vi.fn()} />);

    await selectRecurrence(user, "Annual date");

    // Pick March (03) / 14
    await user.click(screen.getByLabelText("Month"));
    await user.click(await screen.findByRole("option", { name: "03" }));
    await user.click(screen.getByLabelText("Day"));
    await user.click(await screen.findByRole("option", { name: "14" }));

    const submit = screen.getByRole("button", { name: /create|update/i });
    await waitFor(() => expect(submit).not.toBeDisabled());
    await user.click(submit);

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        recurrence_type: "annual_date",
        annual_date: "03-14",
        annual_end_date: null,
        one_off_date: null,
        one_off_end_date: null,
        day_pattern: "all",
      }),
    );
  });

  it("submits annual_date payload with date range", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ScheduleEntryForm pages={mockPages} prefillPageId="page-1" onSubmit={onSubmit} onCancel={vi.fn()} />);

    await selectRecurrence(user, "Annual date");
    await user.click(screen.getByLabelText("Month"));
    await user.click(await screen.findByRole("option", { name: "12" }));
    await user.click(screen.getByLabelText("Day"));
    await user.click(await screen.findByRole("option", { name: "24" }));

    await user.click(screen.getByLabelText("Use a date range"));

    await user.click(screen.getByLabelText("End month"));
    await user.click(await screen.findByRole("option", { name: "12" }));
    await user.click(screen.getByLabelText("End day"));
    await user.click(await screen.findByRole("option", { name: "26" }));

    const submit = screen.getByRole("button", { name: /create|update/i });
    await waitFor(() => expect(submit).not.toBeDisabled());
    await user.click(submit);

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        recurrence_type: "annual_date",
        annual_date: "12-24",
        annual_end_date: "12-26",
      }),
    );
  });

  it("prefills annual_date fields when editing", () => {
    const schedule: ScheduleEntry = {
      ...baseScheduleFields,
      recurrence_type: "annual_date",
      annual_date: "07-04",
      annual_end_date: "07-05",
    };
    render(<ScheduleEntryForm schedule={schedule} pages={mockPages} onSubmit={vi.fn()} onCancel={vi.fn()} />);

    const monthTrigger = screen.getByLabelText("Month");
    const dayTrigger = screen.getByLabelText("Day");
    expect(monthTrigger).toHaveTextContent("07");
    expect(dayTrigger).toHaveTextContent("04");
    // Range switch must be on, end fields populated
    const rangeSwitch = screen.getByLabelText("Use a date range");
    expect(rangeSwitch).toBeChecked();
    expect(screen.getByLabelText("End month")).toHaveTextContent("07");
    expect(screen.getByLabelText("End day")).toHaveTextContent("05");
  });
});

describe("ScheduleEntryForm — one_off_date recurrence", () => {
  it("renders date input after selecting Specific date", async () => {
    const user = userEvent.setup();
    render(<ScheduleEntryForm pages={mockPages} prefillPageId="page-1" onSubmit={vi.fn()} onCancel={vi.fn()} />);

    await selectRecurrence(user, "Specific date");
    expect(screen.getByLabelText("Date")).toBeInTheDocument();
    expect(screen.getByLabelText("Use a date range")).toBeInTheDocument();
  });

  it("shows validation error when one_off date not picked", async () => {
    const user = userEvent.setup();
    render(<ScheduleEntryForm pages={mockPages} prefillPageId="page-1" onSubmit={vi.fn()} onCancel={vi.fn()} />);

    await selectRecurrence(user, "Specific date");
    await waitFor(() => {
      expect(screen.getByText("Please pick a date")).toBeInTheDocument();
    });
  });

  it("submits one_off_date payload with single date", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ScheduleEntryForm pages={mockPages} prefillPageId="page-1" onSubmit={onSubmit} onCancel={vi.fn()} />);

    await selectRecurrence(user, "Specific date");
    const dateInput = screen.getByLabelText("Date") as HTMLInputElement;
    // type="date" inputs accept ISO yyyy-mm-dd via fireEvent change semantics
    await user.clear(dateInput);
    await user.type(dateInput, "2099-08-15");

    const submit = screen.getByRole("button", { name: /create|update/i });
    await waitFor(() => expect(submit).not.toBeDisabled());
    await user.click(submit);

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        recurrence_type: "one_off_date",
        one_off_date: "2099-08-15",
        one_off_end_date: null,
        annual_date: null,
        annual_end_date: null,
      }),
    );
  });

  it("shows error when one_off end date is before start date", async () => {
    const user = userEvent.setup();
    render(<ScheduleEntryForm pages={mockPages} prefillPageId="page-1" onSubmit={vi.fn()} onCancel={vi.fn()} />);

    await selectRecurrence(user, "Specific date");
    const dateInput = screen.getByLabelText("Date") as HTMLInputElement;
    await user.clear(dateInput);
    await user.type(dateInput, "2099-08-15");
    await user.click(screen.getByLabelText("Use a date range"));
    const endInput = screen.getByLabelText("End date") as HTMLInputElement;
    await user.clear(endInput);
    await user.type(endInput, "2099-08-10");

    await waitFor(() => {
      expect(screen.getByText("End date must be on or after start date")).toBeInTheDocument();
    });
  });

  it("submits one_off_date payload with date range", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<ScheduleEntryForm pages={mockPages} prefillPageId="page-1" onSubmit={onSubmit} onCancel={vi.fn()} />);

    await selectRecurrence(user, "Specific date");
    const dateInput = screen.getByLabelText("Date") as HTMLInputElement;
    await user.clear(dateInput);
    await user.type(dateInput, "2099-08-15");
    await user.click(screen.getByLabelText("Use a date range"));
    const endInput = screen.getByLabelText("End date") as HTMLInputElement;
    await user.clear(endInput);
    await user.type(endInput, "2099-08-20");

    const submit = screen.getByRole("button", { name: /create|update/i });
    await waitFor(() => expect(submit).not.toBeDisabled());
    await user.click(submit);

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        recurrence_type: "one_off_date",
        one_off_date: "2099-08-15",
        one_off_end_date: "2099-08-20",
      }),
    );
  });

  it("prefills one_off_date fields when editing", () => {
    const schedule: ScheduleEntry = {
      ...baseScheduleFields,
      recurrence_type: "one_off_date",
      one_off_date: "2099-12-31",
      one_off_end_date: "2100-01-02",
    };
    render(<ScheduleEntryForm schedule={schedule} pages={mockPages} onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByLabelText("Date")).toHaveValue("2099-12-31");
    expect(screen.getByLabelText("Use a date range")).toBeChecked();
    expect(screen.getByLabelText("End date")).toHaveValue("2100-01-02");
  });
});

describe("ScheduleEntryForm — switching back to weekly clears date overrides", () => {
  it("submits weekly payload with annual/one-off fields nulled out", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    const schedule: ScheduleEntry = {
      ...baseScheduleFields,
      recurrence_type: "annual_date",
      annual_date: "01-01",
    };
    render(<ScheduleEntryForm schedule={schedule} pages={mockPages} onSubmit={onSubmit} onCancel={vi.fn()} />);

    await selectRecurrence(user, "Weekly");

    const submit = screen.getByRole("button", { name: /create|update/i });
    await waitFor(() => expect(submit).not.toBeDisabled());
    await user.click(submit);

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1));
    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        recurrence_type: "weekly",
        annual_date: null,
        annual_end_date: null,
        one_off_date: null,
        one_off_end_date: null,
      }),
    );
  });
});

describe("ScheduleEntryForm — recurrence description text", () => {
  it("shows the description for the currently selected recurrence type", async () => {
    const user = userEvent.setup();
    render(<ScheduleEntryForm pages={mockPages} prefillPageId="page-1" onSubmit={vi.fn()} onCancel={vi.fn()} />);

    // Default weekly
    expect(screen.getByText("Repeats on selected days of the week")).toBeInTheDocument();

    await selectRecurrence(user, "Annual date");
    expect(screen.getByText("Repeats every year on a specific date")).toBeInTheDocument();

    await selectRecurrence(user, "Specific date");
    expect(screen.getByText("One-off date that doesn't repeat")).toBeInTheDocument();
  });
});

// Silence unused import lint by referencing within for future use.
void within;
