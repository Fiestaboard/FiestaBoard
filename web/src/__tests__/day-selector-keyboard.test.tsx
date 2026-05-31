import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NextIntlClientProvider } from "next-intl";
import { DaySelector } from "@/components/day-selector";
import en from "../../messages/en.json";
import type { DayPattern } from "@/lib/api";

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <NextIntlClientProvider locale="en" messages={en}>
      {children}
    </NextIntlClientProvider>
  );
}

function renderSelector(value: DayPattern = "all") {
  const onChange = vi.fn();
  render(<DaySelector value={value} onChange={onChange} />, { wrapper: Wrapper });
  return { onChange };
}

describe("DaySelector keyboard navigation", () => {
  it("ArrowDown moves selection to the next pattern", async () => {
    const { onChange } = renderSelector("all");
    (screen.getAllByRole("radio").find((r) => r.getAttribute("aria-checked") === "true")!).focus();
    await userEvent.keyboard("{ArrowDown}");
    expect(onChange).toHaveBeenCalledWith("weekdays", undefined);
  });

  it("ArrowRight also moves selection forward", async () => {
    const { onChange } = renderSelector("weekdays");
    (screen.getAllByRole("radio").find((r) => r.getAttribute("aria-checked") === "true")!).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(onChange).toHaveBeenCalledWith("weekends", undefined);
  });

  it("ArrowUp moves selection to the previous pattern and wraps", async () => {
    const { onChange } = renderSelector("all");
    (screen.getAllByRole("radio").find((r) => r.getAttribute("aria-checked") === "true")!).focus();
    await userEvent.keyboard("{ArrowUp}");
    expect(onChange).toHaveBeenCalledWith("custom", ["monday"]);
  });

  it("ArrowLeft moves selection backward", async () => {
    const { onChange } = renderSelector("weekends");
    (screen.getAllByRole("radio").find((r) => r.getAttribute("aria-checked") === "true")!).focus();
    await userEvent.keyboard("{ArrowLeft}");
    expect(onChange).toHaveBeenCalledWith("weekdays", undefined);
  });

  it("Home jumps to the first pattern", async () => {
    const { onChange } = renderSelector("custom");
    (screen.getAllByRole("radio").find((r) => r.getAttribute("aria-checked") === "true")!).focus();
    await userEvent.keyboard("{Home}");
    expect(onChange).toHaveBeenCalledWith("all", undefined);
  });

  it("End jumps to the last pattern", async () => {
    const { onChange } = renderSelector("all");
    (screen.getAllByRole("radio").find((r) => r.getAttribute("aria-checked") === "true")!).focus();
    await userEvent.keyboard("{End}");
    expect(onChange).toHaveBeenCalledWith("custom", ["monday"]);
  });

  it("ignores unrelated keys", async () => {
    const { onChange } = renderSelector("all");
    (screen.getAllByRole("radio").find((r) => r.getAttribute("aria-checked") === "true")!).focus();
    await userEvent.keyboard("a");
    expect(onChange).not.toHaveBeenCalled();
  });

  it("custom day checkboxes can be toggled on and off", async () => {
    const onChange = vi.fn();
    render(
      <DaySelector
        value="custom"
        customDays={["monday", "tuesday"]}
        onChange={onChange}
      />,
      { wrapper: Wrapper },
    );
    const tuesday = screen.getByRole("checkbox", { name: /tuesday/i });
    await userEvent.click(tuesday);
    expect(onChange).toHaveBeenCalledWith("custom", ["monday"]);

    onChange.mockClear();
    const wednesday = screen.getByRole("checkbox", { name: /wednesday/i });
    await userEvent.click(wednesday);
    expect(onChange).toHaveBeenCalledWith(
      "custom",
      expect.arrayContaining(["monday", "tuesday", "wednesday"]),
    );
  });

  it("refuses to deselect the last remaining custom day", async () => {
    const onChange = vi.fn();
    render(
      <DaySelector value="custom" customDays={["monday"]} onChange={onChange} />,
      { wrapper: Wrapper },
    );
    const monday = screen.getByRole("checkbox", { name: /monday/i });
    await userEvent.click(monday);
    expect(onChange).not.toHaveBeenCalled();
  });
});
