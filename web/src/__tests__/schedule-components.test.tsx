import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { DaySelector } from "@/components/day-selector";

describe("DaySelector", () => {
  it("renders all day pattern options", () => {
    const onChange = vi.fn();
    render(<DaySelector value="all" onChange={onChange} customDays={[]} />);

    expect(screen.getByText("All Days")).toBeInTheDocument();
    expect(screen.getByText("Weekdays (Mon-Fri)")).toBeInTheDocument();
    expect(screen.getByText("Weekends (Sat-Sun)")).toBeInTheDocument();
    expect(screen.getByText("Custom Days")).toBeInTheDocument();
  });

  it("calls onChange when day pattern is selected", () => {
    const onChange = vi.fn();
    render(<DaySelector value="all" onChange={onChange} customDays={[]} />);

    fireEvent.click(screen.getByText("Weekdays (Mon-Fri)"));

    expect(onChange).toHaveBeenCalledWith("weekdays", undefined);
  });

  it("shows custom day checkboxes when 'Custom' is selected", () => {
    const onChange = vi.fn();
    render(<DaySelector value="custom" onChange={onChange} customDays={["monday", "wednesday"]} />);

    // Day labels should be visible (as checkbox labels)
    expect(screen.getByLabelText("Monday")).toBeInTheDocument();
    expect(screen.getByLabelText("Tuesday")).toBeInTheDocument();
    expect(screen.getByLabelText("Wednesday")).toBeInTheDocument();
    expect(screen.getByLabelText("Thursday")).toBeInTheDocument();
    expect(screen.getByLabelText("Friday")).toBeInTheDocument();
    expect(screen.getByLabelText("Saturday")).toBeInTheDocument();
    expect(screen.getByLabelText("Sunday")).toBeInTheDocument();
  });

  it("does not show custom day checkboxes when 'Custom' is not selected", () => {
    const onChange = vi.fn();
    render(<DaySelector value="weekdays" onChange={onChange} customDays={[]} />);

    // Day checkboxes should not be visible
    expect(screen.queryByLabelText("Monday")).not.toBeInTheDocument();
  });

  it("checks the correct custom days", () => {
    const onChange = vi.fn();
    render(<DaySelector value="custom" onChange={onChange} customDays={["monday", "friday"]} />);

    const mondayCheckbox = screen.getByLabelText("Monday") as HTMLInputElement;
    const fridayCheckbox = screen.getByLabelText("Friday") as HTMLInputElement;
    const tuesdayCheckbox = screen.getByLabelText("Tuesday") as HTMLInputElement;

    expect(mondayCheckbox.checked).toBe(true);
    expect(fridayCheckbox.checked).toBe(true);
    expect(tuesdayCheckbox.checked).toBe(false);
  });

  it("calls onChange when a day is checked", () => {
    const onChange = vi.fn();
    render(<DaySelector value="custom" onChange={onChange} customDays={["monday"]} />);

    const tuesdayCheckbox = screen.getByLabelText("Tuesday");
    fireEvent.click(tuesdayCheckbox);

    expect(onChange).toHaveBeenCalledWith("custom", ["monday", "tuesday"]);
  });

  it("calls onChange when a day is unchecked", () => {
    const onChange = vi.fn();
    render(<DaySelector value="custom" onChange={onChange} customDays={["monday", "tuesday", "friday"]} />);

    const tuesdayCheckbox = screen.getByLabelText("Tuesday");
    fireEvent.click(tuesdayCheckbox);

    expect(onChange).toHaveBeenCalledWith("custom", ["monday", "friday"]);
  });
});
