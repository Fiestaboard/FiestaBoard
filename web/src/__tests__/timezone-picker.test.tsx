import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TimezonePicker } from "@/components/ui/timezone-picker";

function currentLAOffset(): string {
  const now = new Date();
  const fmt = new Intl.DateTimeFormat("en-US", { timeZone: "America/Los_Angeles", timeZoneName: "shortOffset" });
  const parts = fmt.formatToParts(now);
  const offsetPart = parts.find((p) => p.type === "timeZoneName");
  return offsetPart?.value?.replace("GMT", "UTC") ?? "UTC-8";
}

describe("TimezonePicker", () => {
  it("renders with default value", () => {
    render(
      <TimezonePicker
        value="America/Los_Angeles"
        onChange={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("Search timezone...");
    expect(input).toBeInTheDocument();
    const offset = currentLAOffset();
    expect(input).toHaveValue(`America/Los Angeles (${offset})`);
  });

  it("displays input field for searching", () => {
    render(
      <TimezonePicker
        value="America/Los_Angeles"
        onChange={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("Search timezone...");
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute("type", "text");
  });

  it("filters timezones as user types", async () => {
    const user = userEvent.setup();
    render(
      <TimezonePicker
        value="America/Los_Angeles"
        onChange={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);
    
    // Wait for initial dropdown to appear
    await waitFor(() => {
      const buttons = screen.queryAllByRole("button");
      const timezoneButtons = buttons.filter(
        (btn) => btn.textContent && btn.textContent.includes("UTC")
      );
      expect(timezoneButtons.length).toBeGreaterThan(0);
    }, { timeout: 3000 });

    // Type to filter
    await user.clear(input);
    await user.type(input, "New York");

    // Wait for filtered results to appear - look for New York in any button
    await waitFor(() => {
      const buttons = screen.queryAllByRole("button");
      const filteredButtons = buttons.filter(
        (btn) => btn.textContent && /New York/i.test(btn.textContent)
      );
      expect(filteredButtons.length).toBeGreaterThan(0);
    }, { timeout: 3000 });
  });

  it("calls onChange when timezone is selected from dropdown", async () => {
    const user = userEvent.setup();
    const handleChange = vi.fn();

    render(
      <TimezonePicker
        value="America/Los_Angeles"
        onChange={handleChange}
      />
    );

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);
    
    // Wait for dropdown to appear
    await waitFor(() => {
      const buttons = screen.queryAllByRole("button");
      const timezoneButtons = buttons.filter(
        (btn) => btn.textContent && btn.textContent.includes("UTC")
      );
      expect(timezoneButtons.length).toBeGreaterThan(0);
    }, { timeout: 3000 });

    // Type to filter for New York
    await user.clear(input);
    await user.type(input, "New York");
    
    // Wait for filtered results
    await waitFor(() => {
      const buttons = screen.queryAllByRole("button");
      const newYorkButton = buttons.find(
        (btn) => btn.textContent && /New York/i.test(btn.textContent)
      );
      expect(newYorkButton).toBeDefined();
    }, { timeout: 3000 });

    // Find and click New York option
    const buttons = screen.queryAllByRole("button");
    const newYorkButton = buttons.find(
      (btn) => btn.textContent && /New York/i.test(btn.textContent)
    );
    expect(newYorkButton).toBeDefined();
    if (newYorkButton) {
      await user.click(newYorkButton);
      expect(handleChange).toHaveBeenCalledWith("America/New_York");
    }
  });

  it("can be disabled", () => {
    render(
      <TimezonePicker
        value="America/Los_Angeles"
        onChange={vi.fn()}
        disabled
      />
    );

    const input = screen.getByPlaceholderText("Search timezone...");
    expect(input).toBeDisabled();
  });

  it("applies custom className", () => {
    const { container } = render(
      <TimezonePicker
        value="America/Los_Angeles"
        onChange={vi.fn()}
        className="custom-class"
      />
    );

    const wrapper = container.querySelector(".custom-class");
    expect(wrapper).toBeInTheDocument();
  });

  it("shows validation error for invalid timezone", async () => {
    const user = userEvent.setup();
    render(
      <TimezonePicker
        value="Invalid/Timezone"
        onChange={vi.fn()}
      />
    );

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

    render(
      <TimezonePicker
        value="America/Los_Angeles"
        onChange={handleChange}
      />
    );

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);

    // Wait for dropdown to appear
    await waitFor(() => {
      const buttons = screen.queryAllByRole("button");
      const timezoneButtons = buttons.filter(
        (btn) => btn.textContent && btn.textContent.includes("UTC")
      );
      expect(timezoneButtons.length).toBeGreaterThan(0);
    }, { timeout: 3000 });

    // Press Arrow Down to navigate
    await user.keyboard("{ArrowDown}");
    
    // Press Enter to select
    await user.keyboard("{Enter}");

    // Should have called onChange (though the exact value depends on filtering)
    expect(handleChange).toHaveBeenCalled();
  });

  it("closes dropdown on Escape key", async () => {
    const user = userEvent.setup();
    render(
      <TimezonePicker
        value="America/Los_Angeles"
        onChange={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);

    // Wait for dropdown to appear
    await waitFor(() => {
      const buttons = screen.queryAllByRole("button");
      const timezoneButtons = buttons.filter(
        (btn) => btn.textContent && btn.textContent.includes("UTC")
      );
      expect(timezoneButtons.length).toBeGreaterThan(0);
    }, { timeout: 3000 });

    // Press Escape
    await user.keyboard("{Escape}");

    // Dropdown should close - timezone buttons should no longer be visible
    await waitFor(() => {
      const buttons = screen.queryAllByRole("button");
      const timezoneButtons = buttons.filter(
        (btn) => btn.textContent && btn.textContent.includes("UTC") && !btn.textContent.includes("Showing first")
      );
      expect(timezoneButtons.length).toBe(0);
    });
  });

  it("filters timezones by name, value, or offset", async () => {
    const user = userEvent.setup();
    render(
      <TimezonePicker
        value="America/Los_Angeles"
        onChange={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);
    
    // Wait for initial dropdown
    await waitFor(() => {
      const buttons = screen.queryAllByRole("button");
      const timezoneButtons = buttons.filter(
        (btn) => btn.textContent && btn.textContent.includes("UTC")
      );
      expect(timezoneButtons.length).toBeGreaterThan(0);
    }, { timeout: 3000 });
    
    // Search by city name
    await user.clear(input);
    await user.type(input, "Tokyo");
    await waitFor(() => {
      const buttons = screen.queryAllByRole("button");
      const tokyoButtons = buttons.filter(
        (btn) => btn.textContent && /Tokyo/i.test(btn.textContent)
      );
      expect(tokyoButtons.length).toBeGreaterThan(0);
    }, { timeout: 3000 });

    // Clear and search by region
    await user.clear(input);
    await user.type(input, "Europe");
    await waitFor(() => {
      const buttons = screen.queryAllByRole("button");
      const europeButtons = buttons.filter(
        (btn) => btn.textContent && /Europe/i.test(btn.textContent)
      );
      expect(europeButtons.length).toBeGreaterThan(0);
    }, { timeout: 3000 });
  });

  it("calls onValidationChange when validation state changes", async () => {
    const user = userEvent.setup();
    const onValidationChange = vi.fn();

    render(
      <TimezonePicker
        value="America/Los_Angeles"
        onChange={vi.fn()}
        onValidationChange={onValidationChange}
      />
    );

    const input = screen.getByPlaceholderText("Search timezone...");
    
    // Type an invalid timezone
    await user.type(input, "InvalidTimezone123");
    
    // Should notify about invalid state
    await waitFor(() => {
      expect(onValidationChange).toHaveBeenCalled();
    });
  });

  it("handles empty value gracefully", () => {
    render(
      <TimezonePicker
        value=""
        onChange={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("Search timezone...");
    expect(input).toBeInTheDocument();
    expect(input).toHaveValue("");
  });

  it("shows dropdown when input is focused", async () => {
    const user = userEvent.setup();
    render(
      <TimezonePicker
        value="America/Los_Angeles"
        onChange={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);

    // Dropdown should appear
    await waitFor(() => {
      const dropdown = screen.queryByText(/America\/Los Angeles/i);
      expect(dropdown).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("limits displayed results to 50 items", async () => {
    const user = userEvent.setup();
    render(
      <TimezonePicker
        value=""
        onChange={vi.fn()}
      />
    );

    const input = screen.getByPlaceholderText("Search timezone...");
    await user.click(input);

    // Wait for dropdown - look for any timezone button
    await waitFor(() => {
      const buttons = screen.queryAllByRole("button");
      const timezoneButtons = buttons.filter(
        (btn) => btn.textContent && btn.textContent.includes("UTC")
      );
      expect(timezoneButtons.length).toBeGreaterThan(0);
    }, { timeout: 3000 });

    // Count visible timezone options (excluding the "Showing first 50" message if present)
    const timezoneButtons = screen.queryAllByRole("button").filter(
      (btn) => btn.textContent && !btn.textContent.includes("Showing first") && btn.textContent.includes("UTC")
    );
    
    // Should show at most 50 items plus the message if there are more
    expect(timezoneButtons.length).toBeLessThanOrEqual(50);
  });
});
