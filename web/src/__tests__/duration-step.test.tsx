import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { defaultDurationChoice, DurationStep } from "@/components/home/duration-step";

const NOW = new Date(2026, 10, 13, 18, 16, 0);
const NINE_PM = new Date(2026, 10, 13, 21, 0, 0);

function renderStep(props: Partial<React.ComponentProps<typeof DurationStep>> = {}) {
  const onValueChange = vi.fn();
  render(
    <DurationStep
      name="Taco Tuesday"
      value="next-change"
      onValueChange={onValueChange}
      nextChange={{ at: NINE_PM, pageId: "good-night" }}
      nextPageName="Good night"
      scheduleEnabled
      now={NOW}
      {...props}
    />,
  );
  return { onValueChange };
}

describe("DurationStep", () => {
  it("asks the question for the named page and offers CANON's four chips", () => {
    renderStep();
    const group = screen.getByRole("radiogroup", { name: "How long should Taco Tuesday stay up?" });
    expect(group).toBeInTheDocument();
    const labels = screen.getAllByRole("radio").map((r) => r.textContent?.trim());
    expect(labels).toEqual(["15 min", "1 hr", "Until 9:00 PM", "Until I cancel"]);
  });

  it("names the Schedule's next page in the outcome of the next-change chip", () => {
    renderStep();
    expect(
      screen.getByText("Holds until 9:00 PM (2h 44m), then Schedule resumes with Good night."),
    ).toBeInTheDocument();
  });

  it("leaves out the next-change chip when the hub predicts no Schedule change", () => {
    renderStep({ nextChange: null, value: "1h" });
    const labels = screen.getAllByRole("radio").map((r) => r.textContent?.trim());
    expect(labels).toEqual(["15 min", "1 hr", "Until I cancel"]);
    expect(screen.getByText("Holds until 7:16 PM (1h), then Schedule resumes.")).toBeInTheDocument();
  });

  it("says what comes back after a timed hold in Manual Mode", () => {
    renderStep({ scheduleEnabled: false, nextChange: null, value: "15m", manualPageName: "Evening commute" });
    expect(screen.getByText("Holds until 6:31 PM (15m), then Evening commute comes back.")).toBeInTheDocument();
  });

  it("says Until I cancel holds until a cancel, or pins in Manual Mode when asked to", () => {
    const { unmount } = render(
      <DurationStep value="until-cancel" onValueChange={vi.fn()} nextChange={null} scheduleEnabled now={NOW} />,
    );
    expect(screen.getByText("Holds until you cancel or Change Page again.")).toBeInTheDocument();
    unmount();
    render(
      <DurationStep
        value="until-cancel"
        onValueChange={vi.fn()}
        nextChange={null}
        scheduleEnabled={false}
        untilCancelPins
        now={NOW}
      />,
    );
    expect(screen.getByText("Stays until you change it. Schedule Mode stays off.")).toBeInTheDocument();
  });

  it("says a new hold replaces the running Override", () => {
    renderStep({ value: "1h", replacesName: "Focus time" });
    expect(screen.getByText(/Replaces the Focus time Override\.$/)).toBeInTheDocument();
  });

  it("reports the chosen chip", () => {
    const { onValueChange } = renderStep();
    fireEvent.click(screen.getByRole("radio", { name: "1 hr" }));
    expect(onValueChange).toHaveBeenCalledWith("1h");
  });

  it("asks a generic question when no name is given", () => {
    renderStep({ name: undefined });
    expect(screen.getByRole("radiogroup", { name: "How long should it stay up?" })).toBeInTheDocument();
  });
});

describe("defaultDurationChoice", () => {
  it("preselects the next change when there is one (07a)", () => {
    expect(defaultDurationChoice({ at: NINE_PM, pageId: null }, { scheduleEnabled: true })).toBe("next-change");
  });

  it("falls back to 1 hr in Schedule Mode and to Until I cancel in Manual Mode", () => {
    expect(defaultDurationChoice(null, { scheduleEnabled: true })).toBe("1h");
    expect(defaultDurationChoice(null, { scheduleEnabled: false })).toBe("until-cancel");
  });
});
