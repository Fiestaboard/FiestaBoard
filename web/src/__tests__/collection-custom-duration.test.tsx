/**
 * Tests for the custom page-duration entry in the collection form (issue #1652).
 *
 * The duration Select used to top out at 30 minutes with no way to type a
 * value. It now offers presets up to 24 hours plus a "Custom…" option that
 * reveals an amount + unit entry, validated against the same 5s–24h range the
 * API enforces (src/collections/models.py).
 */

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { Collection, Page } from "@/lib/api";

import { CollectionForm, formatInterval, parseCustomInterval, splitInterval } from "../../app/routes/collections";

vi.mock("sonner", () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), loading: vi.fn() },
  Toaster: () => null,
}));

const mockPages = [
  { id: "page-1", name: "Page One" },
  { id: "page-2", name: "Page Two" },
] as unknown as Page[];

function makeCollection(intervalSeconds: number): Collection {
  return {
    id: "collection:c1",
    name: "Rotation",
    page_ids: ["page-1", "page-2"],
    selection_mode: "time",
    time: { interval_seconds: intervalSeconds },
    variable: null,
    random: null,
    created_at: "2025-01-01T00:00:00Z",
  } as Collection;
}

function renderForm(collection?: Collection, onSubmit = vi.fn()) {
  render(<CollectionForm collection={collection} pages={mockPages} onSubmit={onSubmit} onCancel={vi.fn()} />);
  return onSubmit;
}

/** Open the page-duration Select and click the option with the given label. */
async function chooseDuration(user: ReturnType<typeof userEvent.setup>, optionName: string) {
  await user.click(screen.getByLabelText("Page Duration"));
  await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
  await user.click(screen.getByRole("option", { name: optionName }));
}

// ---------------------------------------------------------------------------
// Pure helpers
// ---------------------------------------------------------------------------

describe("parseCustomInterval", () => {
  it("converts an amount plus unit into seconds", () => {
    expect(parseCustomInterval("2", "hours")).toBe(7200);
    expect(parseCustomInterval("90", "minutes")).toBe(5400);
    expect(parseCustomInterval("45", "seconds")).toBe(45);
  });

  it("accepts exactly 24 hours", () => {
    expect(parseCustomInterval("24", "hours")).toBe(86400);
  });

  it("rejects a duration longer than 24 hours", () => {
    expect(parseCustomInterval("25", "hours")).toBeNull();
    expect(parseCustomInterval("1441", "minutes")).toBeNull();
  });

  it("rejects a duration shorter than the 5 second floor", () => {
    expect(parseCustomInterval("4", "seconds")).toBeNull();
  });

  it("rejects entries that are not whole numbers", () => {
    expect(parseCustomInterval("1.5", "hours")).toBeNull();
    expect(parseCustomInterval("", "minutes")).toBeNull();
    expect(parseCustomInterval("abc", "minutes")).toBeNull();
  });
});

describe("splitInterval", () => {
  it("uses the largest unit that divides the duration exactly", () => {
    expect(splitInterval(7200)).toEqual({ amount: 2, unit: "hours" });
    expect(splitInterval(5400)).toEqual({ amount: 90, unit: "minutes" });
    expect(splitInterval(45)).toEqual({ amount: 45, unit: "seconds" });
  });
});

describe("formatInterval", () => {
  it("renders durations of an hour or more in hours and minutes", () => {
    expect(formatInterval(3600)).toBe("1h");
    expect(formatInterval(5400)).toBe("1h 30m");
    expect(formatInterval(86400)).toBe("24h");
  });
});

// ---------------------------------------------------------------------------
// Custom duration UI
// ---------------------------------------------------------------------------

describe("CollectionForm page duration", () => {
  it("offers presets beyond 30 minutes", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByLabelText("Page Duration"));
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());

    expect(screen.getByRole("option", { name: "1 hour" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "24 hours" })).toBeInTheDocument();
  });

  it("reveals the custom duration entry when Custom is selected", async () => {
    const user = userEvent.setup();
    renderForm();

    expect(screen.queryByLabelText("Custom duration")).not.toBeInTheDocument();

    await chooseDuration(user, "Custom…");

    await waitFor(() => expect(screen.getByLabelText("Custom duration")).toBeInTheDocument());
    expect(screen.getByLabelText("Unit")).toBeInTheDocument();
  });

  it("submits a custom duration converted to seconds", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderForm(makeCollection(30), onSubmit);

    await chooseDuration(user, "Custom…");
    const amount = await screen.findByLabelText("Custom duration");
    await user.clear(amount);
    await user.type(amount, "3");

    await user.click(screen.getByLabelText("Unit"));
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    await user.click(screen.getByRole("option", { name: "Hours" }));

    await user.click(screen.getByRole("button", { name: "Update Collection" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].time).toEqual({ interval_seconds: 10800 });
  });

  it("rejects a custom duration above 24 hours", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderForm(makeCollection(30), onSubmit);

    await chooseDuration(user, "Custom…");
    const amount = await screen.findByLabelText("Custom duration");
    await user.clear(amount);
    await user.type(amount, "48");

    await user.click(screen.getByLabelText("Unit"));
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    await user.click(screen.getByRole("option", { name: "Hours" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Enter a whole number between 5 seconds and 24 hours."),
    );
    expect(screen.getByRole("button", { name: "Update Collection" })).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("rejects a custom duration below the 5 second floor", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderForm(makeCollection(30), onSubmit);

    await chooseDuration(user, "Custom…");
    const amount = await screen.findByLabelText("Custom duration");
    await user.clear(amount);
    await user.type(amount, "2");

    await user.click(screen.getByLabelText("Unit"));
    await waitFor(() => expect(screen.getByRole("listbox")).toBeInTheDocument());
    await user.click(screen.getByRole("option", { name: "Seconds" }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Update Collection" })).toBeDisabled();
  });

  it("opens in custom mode for a collection whose interval is not a preset", async () => {
    renderForm(makeCollection(5400));

    const amount = await screen.findByLabelText("Custom duration");
    expect(amount).toHaveValue(90);
    expect(screen.getByLabelText("Unit")).toHaveTextContent("Minutes");
  });

  it("keeps a preset interval on the preset Select rather than custom mode", () => {
    renderForm(makeCollection(1800));

    expect(screen.queryByLabelText("Custom duration")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Page Duration")).toHaveTextContent("30 minutes");
  });

  it("preserves a non-preset interval when saved without touching the duration", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    renderForm(makeCollection(5400), onSubmit);

    await user.click(screen.getByRole("button", { name: "Update Collection" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].time).toEqual({ interval_seconds: 5400 });
  });
});
