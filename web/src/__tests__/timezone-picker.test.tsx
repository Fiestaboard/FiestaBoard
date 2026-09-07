import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TimezonePicker } from "@/components/ui/timezone-picker";

function currentLAOffset(): string {
  const now = new Date();
  const fmt = new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", timeZoneName: "shortOffset" });
  const parts = fmt.formatToParts(now);
  const offsetPart = parts.find((p) => p.type === "timeZoneName");
  return offsetPart?.value?.replace("GMT", "UTC") ?? "UTC-8";
}

/**
 * The zone rows. They are the combobox's `role="option"` items — the picker is
 * a real combobox now, not a portal full of buttons — and every label carries
 * its offset ("America/Los Angeles (UTC-8)"), which is what identifies a row
 * as a zone rather than chrome.
 */
function zoneOptions(): HTMLElement[] {
  return screen.queryAllByRole("option").filter((option) => option.textContent?.includes("UTC"));
}

describe("TimezonePicker", () => {
  it("renders with default value", () => {
    render(<TimezonePicker value="America/Los_Angeles" onChange={vi.fn()} />);

    const input = screen.getByPlaceholderText("Search timezone...");
    expect(input).toBeInTheDocument();
    const offset = currentLAOffset();
    expect(input).toHaveValue(`America/Los Angeles (${offset})`);
  });

  it("displays input field for searching", () => {
    render(<TimezonePicker value="America/Los_Angeles" onChange={vi.fn()} />);

    const input = screen.getByPlaceholderText("Search timezone...");
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("type", "text");
  });

  it("filters timezones as user types", async () => {
    const user = userEvent.setup();
    render(<TimezonePicker value="America/Los_Angeles" onChange={vi.fn()} />);

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);

    // Wait for initial dropdown to appear
    await waitFor(() => expect(zoneOptions().length).toBeGreaterThan(0), { timeout: 3000 });

    // Type to filter
    await user.clear(input);
    await user.type(input, "New York");

    // Wait for filtered results to appear - look for New York in any button
    await waitFor(
      () => expect(zoneOptions().filter((option) => /New York/i.test(option.textContent ?? ""))).not.toHaveLength(0),
      { timeout: 3000 },
    );
  });

  it("calls onChange when timezone is selected from dropdown", async () => {
    const user = userEvent.setup();
    const handleChange = vi.fn();

    render(<TimezonePicker value="America/Los_Angeles" onChange={handleChange} />);

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);

    // Wait for dropdown to appear
    await waitFor(() => expect(zoneOptions().length).toBeGreaterThan(0), { timeout: 3000 });

    // Type to filter for New York
    await user.clear(input);
    await user.type(input, "New York");

    // Wait for filtered results
    await waitFor(() => expect(screen.getByRole("option", { name: /New York/i })).toBeInTheDocument(), {
      timeout: 3000,
    });

    await user.click(screen.getByRole("option", { name: /New York/i }));
    expect(handleChange).toHaveBeenCalledWith("America/New_York");
  });

  it("can be disabled", () => {
    render(<TimezonePicker value="America/Los_Angeles" onChange={vi.fn()} disabled />);

    const input = screen.getByPlaceholderText("Search timezone...");
    expect(input).toBeDisabled();
  });

  it("applies custom className", () => {
    const { container } = render(
      <TimezonePicker value="America/Los_Angeles" onChange={vi.fn()} className="custom-class" />,
    );

    const wrapper = container.querySelector(".custom-class");
    expect(wrapper).toBeInTheDocument();
  });

  it("shows validation error for invalid timezone", async () => {
    const user = userEvent.setup();
    render(<TimezonePicker value="Invalid/Timezone" onChange={vi.fn()} />);

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);

    await waitFor(() => {
      const errorMessage = screen.getByText(/Invalid timezone/i);
      expect(errorMessage).toBeInTheDocument();
    });
  });

  it("handles arrow key navigation", async () => {
    const user = userEvent.setup();
    const handleChange = vi.fn();

    render(<TimezonePicker value="America/Los_Angeles" onChange={handleChange} />);

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);

    // Wait for dropdown to appear
    await waitFor(() => expect(zoneOptions().length).toBeGreaterThan(0), { timeout: 3000 });

    // Press Arrow Down to navigate
    await user.keyboard("{ArrowDown}");

    // Press Enter to select
    await user.keyboard("{Enter}");

    // Should have called onChange (though the exact value depends on filtering)
    expect(handleChange).toHaveBeenCalled();
  });

  it("closes dropdown on Escape key", async () => {
    const user = userEvent.setup();
    render(<TimezonePicker value="America/Los_Angeles" onChange={vi.fn()} />);

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);

    // Wait for dropdown to appear
    await waitFor(() => expect(zoneOptions().length).toBeGreaterThan(0), { timeout: 3000 });

    // Press Escape
    await user.keyboard("{Escape}");

    // Dropdown should close - zone rows should no longer be visible
    await waitFor(() => expect(zoneOptions()).toHaveLength(0));
  });

  it("filters timezones by name, value, or offset", async () => {
    const user = userEvent.setup();
    render(<TimezonePicker value="America/Los_Angeles" onChange={vi.fn()} />);

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);

    // Wait for initial dropdown
    await waitFor(() => expect(zoneOptions().length).toBeGreaterThan(0), { timeout: 3000 });

    // Search by city name
    await user.clear(input);
    await user.type(input, "Tokyo");
    await waitFor(
      () => expect(zoneOptions().filter((option) => /Tokyo/i.test(option.textContent ?? ""))).not.toHaveLength(0),
      { timeout: 3000 },
    );

    // Clear and search by region
    await user.clear(input);
    await user.type(input, "Europe");
    await waitFor(
      () => expect(zoneOptions().filter((option) => /Europe/i.test(option.textContent ?? ""))).not.toHaveLength(0),
      { timeout: 3000 },
    );
  });

  it("calls onValidationChange when validation state changes", async () => {
    const user = userEvent.setup();
    const onValidationChange = vi.fn();

    render(<TimezonePicker value="America/Los_Angeles" onChange={vi.fn()} onValidationChange={onValidationChange} />);

    const input = screen.getByPlaceholderText("Search timezone...");

    // Type an invalid timezone
    await user.type(input, "InvalidTimezone123");

    // Should notify about invalid state
    await waitFor(() => {
      expect(onValidationChange).toHaveBeenCalled();
    });
  });

  it("handles empty value gracefully", () => {
    render(<TimezonePicker value="" onChange={vi.fn()} />);

    const input = screen.getByPlaceholderText("Search timezone...");
    expect(input).toBeInTheDocument();
    expect(input).toHaveValue("");
  });

  it("shows dropdown when input is focused", async () => {
    const user = userEvent.setup();
    render(<TimezonePicker value="America/Los_Angeles" onChange={vi.fn()} />);

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);

    // Dropdown should appear
    await waitFor(
      () => {
        const dropdown = screen.queryByText(/America\/Los Angeles/i);
        expect(dropdown).toBeInTheDocument();
      },
      { timeout: 3000 },
    );
  });

  it("limits displayed results to 50 items", async () => {
    const user = userEvent.setup();
    render(<TimezonePicker value="" onChange={vi.fn()} />);

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);

    // Wait for dropdown - look for any zone row
    await waitFor(() => expect(zoneOptions().length).toBeGreaterThan(0), { timeout: 3000 });

    // Should render at most 50 rows even though the zone table is far longer
    expect(zoneOptions().length).toBeLessThanOrEqual(50);
  });

  it("does not call onChange with partial/invalid text while typing", async () => {
    // Regression test for: typing in the search box should NOT propagate invalid
    // timezone strings to the parent (which would cause a 400 on config save).
    const user = userEvent.setup();
    const handleChange = vi.fn();

    render(<TimezonePicker value="America/Los_Angeles" onChange={handleChange} />);

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);

    // Clear and type partial search text (not a valid IANA timezone)
    await user.clear(input);
    await user.type(input, "Los Ang");

    // onChange should NOT have been called with any partial/invalid value
    const invalidCalls = handleChange.mock.calls.filter(([v]) => v !== "America/Los_Angeles" && v !== "");
    expect(invalidCalls).toHaveLength(0);
  });
});
