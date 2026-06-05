import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { TimePicker } from "@/components/ui/time-picker";

describe("TimePicker", () => {
  it("renders with placeholder when no value", () => {
    const onChange = vi.fn();
    render(<TimePicker value="" onChange={onChange} placeholder="00:00" />);

    expect(screen.getByText("00:00")).toBeInTheDocument();
  });

  it("displays time in 12-hour format", () => {
    const onChange = vi.fn();
    render(<TimePicker value="20:00" onChange={onChange} />);

    // Should display as "8:00 PM"
    expect(screen.getByText("8:00 PM")).toBeInTheDocument();
  });

  it("displays midnight correctly", () => {
    const onChange = vi.fn();
    render(<TimePicker value="00:00" onChange={onChange} />);

    expect(screen.getByText("12:00 AM")).toBeInTheDocument();
  });

  it("displays noon correctly", () => {
    const onChange = vi.fn();
    render(<TimePicker value="12:00" onChange={onChange} />);

    expect(screen.getByText("12:00 PM")).toBeInTheDocument();
  });

  it("opens dropdown when clicked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TimePicker value="20:00" onChange={onChange} />);

    const button = screen.getByRole("button");
    await user.click(button);

    await waitFor(() => {
      expect(screen.getByText("Hour")).toBeInTheDocument();
      expect(screen.getByText("Minute")).toBeInTheDocument();
    });
  });

  it("calls onChange when hour is selected", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TimePicker value="20:00" onChange={onChange} />);

    const button = screen.getByRole("button");
    await user.click(button);

    await waitFor(() => {
      expect(screen.getByText("Hour")).toBeInTheDocument();
    });

    // Click on a different hour (e.g., "9 PM" which is 21:00)
    const hourButton = screen.getByText("9 PM");
    await user.click(hourButton);

    // Should call onChange with new hour but keep minutes
    expect(onChange).toHaveBeenCalledWith("21:00");
  });

  it("calls onChange when minute is selected", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TimePicker value="20:00" onChange={onChange} />);

    const button = screen.getByRole("button");
    await user.click(button);

    await waitFor(() => {
      expect(screen.getByText("Minute")).toBeInTheDocument();
    });

    // Click on a different minute (e.g., "05")
    const minuteButton = screen.getByText("05");
    await user.click(minuteButton);

    // Should call onChange with new minute but keep hours
    expect(onChange).toHaveBeenCalledWith("20:05");
  });

  it("has quick preset buttons", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TimePicker value="20:00" onChange={onChange} />);

    const button = screen.getByRole("button");
    await user.click(button);

    await waitFor(() => {
      expect(screen.getByText("Quick presets")).toBeInTheDocument();
    });

    // Check for preset buttons - they appear in both hour selector and presets
    // So we check that they exist (multiple instances is expected)
    expect(screen.getAllByText("8 AM").length).toBeGreaterThan(0);
    expect(screen.getAllByText("12 PM").length).toBeGreaterThan(0);
    expect(screen.getAllByText("6 PM").length).toBeGreaterThan(0);
    expect(screen.getAllByText("8 PM").length).toBeGreaterThan(0);
  });

  it("applies preset time when clicked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<TimePicker value="20:00" onChange={onChange} />);

    const button = screen.getByRole("button");
    await user.click(button);

    await waitFor(() => {
      expect(screen.getByText("Quick presets")).toBeInTheDocument();
    });

    // Find all buttons with "6 PM" text - one in hour selector, one in presets
    // Click the last one which should be the preset button
    const buttons = screen.getAllByText("6 PM");
    const presetButton = buttons[buttons.length - 1];
    await user.click(presetButton);

    expect(onChange).toHaveBeenCalledWith("18:00");
  });
});
