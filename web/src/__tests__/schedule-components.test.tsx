import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PagePickerDialog } from "@/components/page-picker-dialog";
import { DaySelector } from "@/components/day-selector";

describe("PagePickerDialog", () => {
  const mockPages = [
    { id: "page1", name: "Morning Dashboard", type: "template" },
    { id: "page2", name: "Afternoon Dashboard", type: "template" },
    { id: "page3", name: "Evening Dashboard", type: "plugin" },
  ];

  it("renders all pages", () => {
    const onSelect = vi.fn();
    render(
      <PagePickerDialog
        pages={mockPages}
        selectedPageId={null}
        onSelect={onSelect}
      />
    );

    expect(screen.getByText("Morning Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Afternoon Dashboard")).toBeInTheDocument();
    expect(screen.getByText("Evening Dashboard")).toBeInTheDocument();
  });

  it("shows selected page with check mark", () => {
    const onSelect = vi.fn();
    render(
      <PagePickerDialog
        pages={mockPages}
        selectedPageId="page2"
        onSelect={onSelect}
      />
    );

    // The selected page's container should have border-primary class
    const page2Button = screen.getByText("Afternoon Dashboard").closest("button");
    expect(page2Button).toHaveClass("border-primary");
  });

  it("calls onSelect when page is clicked", () => {
    const onSelect = vi.fn();
    render(
      <PagePickerDialog
        pages={mockPages}
        selectedPageId={null}
        onSelect={onSelect}
      />
    );

    fireEvent.click(screen.getByText("Morning Dashboard"));

    expect(onSelect).toHaveBeenCalledWith("page1");
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("does NOT navigate to edit page when clicked (regression test)", () => {
    const onSelect = vi.fn();
    const { container } = render(
      <PagePickerDialog
        pages={mockPages}
        selectedPageId={null}
        onSelect={onSelect}
      />
    );

    fireEvent.click(screen.getByText("Morning Dashboard"));

    // Ensure it called onSelect and not a navigation function
    expect(onSelect).toHaveBeenCalledWith("page1");
    
    // Verify no anchor tags are present (which would indicate navigation)
    expect(container.querySelector("a")).toBeNull();
  });

  it("shows 'None' option when allowNone is true", () => {
    const onSelect = vi.fn();
    render(
      <PagePickerDialog
        pages={mockPages}
        selectedPageId={null}
        onSelect={onSelect}
        allowNone={true}
      />
    );

    expect(screen.getByText("None (no default)")).toBeInTheDocument();
  });

  it("does not show 'None' option when allowNone is false", () => {
    const onSelect = vi.fn();
    render(
      <PagePickerDialog
        pages={mockPages}
        selectedPageId={null}
        onSelect={onSelect}
        allowNone={false}
      />
    );

    expect(screen.queryByText("None (no default)")).not.toBeInTheDocument();
  });

  it("calls onSelect with null when 'None' is clicked", () => {
    const onSelect = vi.fn();
    render(
      <PagePickerDialog
        pages={mockPages}
        selectedPageId="page1"
        onSelect={onSelect}
        allowNone={true}
      />
    );

    fireEvent.click(screen.getByText("None (no default)"));

    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("shows check mark on 'None' when selectedPageId is null", () => {
    const onSelect = vi.fn();
    render(
      <PagePickerDialog
        pages={mockPages}
        selectedPageId={null}
        onSelect={onSelect}
        allowNone={true}
      />
    );

    const noneButton = screen.getByText("None (no default)").closest("button");
    expect(noneButton).toHaveClass("border-primary");
  });

  it("displays page types as badges", () => {
    const onSelect = vi.fn();
    render(
      <PagePickerDialog
        pages={mockPages}
        selectedPageId={null}
        onSelect={onSelect}
      />
    );

    // Use getAllByText since there are multiple pages with "template" type
    const templateBadges = screen.getAllByText("template");
    expect(templateBadges.length).toBe(2);
    expect(screen.getByText("plugin")).toBeInTheDocument();
  });
});

describe("DaySelector", () => {
  it("renders all day pattern options", () => {
    const onChange = vi.fn();
    render(
      <DaySelector
        value="all"
        onChange={onChange}
        customDays={[]}
      />
    );

    expect(screen.getByText("All Days")).toBeInTheDocument();
    expect(screen.getByText("Weekdays (Mon-Fri)")).toBeInTheDocument();
    expect(screen.getByText("Weekends (Sat-Sun)")).toBeInTheDocument();
    expect(screen.getByText("Custom Days")).toBeInTheDocument();
  });

  it("calls onChange when day pattern is selected", () => {
    const onChange = vi.fn();
    render(
      <DaySelector
        value="all"
        onChange={onChange}
        customDays={[]}
      />
    );

    fireEvent.click(screen.getByText("Weekdays (Mon-Fri)"));

    expect(onChange).toHaveBeenCalledWith("weekdays", undefined);
  });

  it("shows custom day checkboxes when 'Custom' is selected", () => {
    const onChange = vi.fn();
    render(
      <DaySelector
        value="custom"
        onChange={onChange}
        customDays={["monday", "wednesday"]}
      />
    );

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
    render(
      <DaySelector
        value="weekdays"
        onChange={onChange}
        customDays={[]}
      />
    );

    // Day checkboxes should not be visible
    expect(screen.queryByLabelText("Monday")).not.toBeInTheDocument();
  });

  it("checks the correct custom days", () => {
    const onChange = vi.fn();
    render(
      <DaySelector
        value="custom"
        onChange={onChange}
        customDays={["monday", "friday"]}
      />
    );

    const mondayCheckbox = screen.getByLabelText("Monday") as HTMLInputElement;
    const fridayCheckbox = screen.getByLabelText("Friday") as HTMLInputElement;
    const tuesdayCheckbox = screen.getByLabelText("Tuesday") as HTMLInputElement;

    expect(mondayCheckbox.checked).toBe(true);
    expect(fridayCheckbox.checked).toBe(true);
    expect(tuesdayCheckbox.checked).toBe(false);
  });

  it("calls onChange when a day is checked", () => {
    const onChange = vi.fn();
    render(
      <DaySelector
        value="custom"
        onChange={onChange}
        customDays={["monday"]}
      />
    );

    const tuesdayCheckbox = screen.getByLabelText("Tuesday");
    fireEvent.click(tuesdayCheckbox);

    expect(onChange).toHaveBeenCalledWith("custom", ["monday", "tuesday"]);
  });

  it("calls onChange when a day is unchecked", () => {
    const onChange = vi.fn();
    render(
      <DaySelector
        value="custom"
        onChange={onChange}
        customDays={["monday", "tuesday", "friday"]}
      />
    );

    const tuesdayCheckbox = screen.getByLabelText("Tuesday");
    fireEvent.click(tuesdayCheckbox);

    expect(onChange).toHaveBeenCalledWith("custom", ["monday", "friday"]);
  });
});

describe("Schedule Component Integration", () => {
  it("PagePickerDialog works independently without PageSelector navigation", () => {
    const onSelect = vi.fn();
    const pages = [
      { id: "page1", name: "Test Page" }
    ];

    render(
      <PagePickerDialog
        pages={pages}
        selectedPageId={null}
        onSelect={onSelect}
      />
    );

    const pageButton = screen.getByText("Test Page");
    fireEvent.click(pageButton);

    // Key assertion: onSelect is called with page ID, not navigation
    expect(onSelect).toHaveBeenCalledWith("page1");
    expect(onSelect).toHaveBeenCalledTimes(1);
  });
});
