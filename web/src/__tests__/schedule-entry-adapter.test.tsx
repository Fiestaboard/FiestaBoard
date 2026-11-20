import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

import { ScheduleEntryAdapter } from "@/components/schedule/schedule-entry-adapter";
import type { ScheduleFormHandle } from "@/components/schedule-editor-bridge-context";
import type { ScheduleEntry } from "@/lib/api";
vi.mock("@/components/current-board-context", () => ({
  useCurrentBoard: () => ({ currentBoard: { id: "note", name: "Desk", device_type: "note" } }),
}));
const pages = [
  { id: "small", name: "Note page", device_type: "note" },
  { id: "big", name: "Flagship page", device_type: "flagship" },
];
const schedule = {
  id: "entry",
  page_id: "small",
  start_time: "09:00",
  end_time: "13:00",
  day_pattern: "all",
  enabled: true,
  edit_protocol: "schedule-revision-v1",
  revision: "original",
} as ScheduleEntry;
describe("Kit schedule entry host adapter", () => {
  it("uses kit segmented time/repeat choices and preserves AI field updates and original edit revision", async () => {
    const ref = createRef<ScheduleFormHandle>();
    const submit = vi.fn().mockResolvedValue(undefined);
    render(<ScheduleEntryAdapter ref={ref} schedule={schedule} pages={pages} onSubmit={submit} onCancel={vi.fn()} />);
    expect(screen.getByRole("radiogroup", { name: "Start time type" })).toBeInTheDocument();
    act(() => {
      ref.current!.setField("start_time", "10:15");
      ref.current!.setField("end_time", null);
      ref.current!.setField("enabled", false);
    });
    expect(screen.getByLabelText("Start Time")).toHaveValue("10:15");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() =>
      expect(submit).toHaveBeenCalledWith(
        expect.objectContaining({ start_time: "10:15", end_time: null, enabled: false, expected_revision: "original" }),
      ),
    );
  });
  it("reveals the kit fallback repair input when a saved solar fallback is invalid", async () => {
    render(
      <ScheduleEntryAdapter
        schedule={{ ...schedule, start_type: "sunrise", start_time: "invalid" }}
        pages={pages}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByLabelText("Start fallback time")).toBeInTheDocument();
  });
  it("filters targets to the board while preserving an already selected incompatible target and warning", () => {
    render(
      <ScheduleEntryAdapter
        schedule={{ ...schedule, page_id: "big" }}
        pages={pages}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(screen.getByRole("combobox", { name: /^Page or Collection/ })).toHaveTextContent("Flagship page");
    expect(screen.getByText(/doesn't match this board's size/)).toBeInTheDocument();
  });
  it("keeps controlled values and permits retry after a rejected revision-aware save", async () => {
    const submit = vi.fn().mockRejectedValueOnce(new Error("Revision changed")).mockResolvedValue(undefined);
    render(<ScheduleEntryAdapter schedule={schedule} pages={pages} onSubmit={submit} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Revision changed");
    expect(screen.getByLabelText("Start Time")).toHaveValue("09:00");
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(2));
  });
});

it("keeps AI spotlight anchors on the actual kit controls", () => {
  render(<ScheduleEntryAdapter schedule={schedule} pages={pages} onSubmit={vi.fn()} onCancel={vi.fn()} />);
  expect(screen.getByLabelText("Start Time")).toHaveAttribute("data-ai-anchor", "schedule.form.start-time");
  expect(screen.getByRole("radiogroup", { name: "Start time type" })).toHaveAttribute(
    "data-ai-anchor",
    "schedule.form.start-type",
  );
});

it.each([
  {
    recurrence_type: "annual_date",
    annual_date: "02-10",
    annual_end_date: "02-12",
    one_off_date: null,
    one_off_end_date: null,
  },
  {
    recurrence_type: "one_off_date",
    annual_date: null,
    annual_end_date: null,
    one_off_date: "2026-11-18",
    one_off_end_date: "2026-11-20",
  },
] as const)("preserves the stored $recurrence_type date range through the kit form", async (dates) => {
  const submit = vi.fn().mockResolvedValue(undefined);
  render(
    <ScheduleEntryAdapter schedule={{ ...schedule, ...dates }} pages={pages} onSubmit={submit} onCancel={vi.fn()} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(submit).toHaveBeenCalledWith(expect.objectContaining({ ...dates, expected_revision: "original" })),
  );
});
it("stages custom days, solar offsets and page values through the existing AI handle", async () => {
  const ref = createRef<ScheduleFormHandle>();
  const submit = vi.fn().mockResolvedValue(undefined);
  render(<ScheduleEntryAdapter ref={ref} schedule={schedule} pages={pages} onSubmit={submit} onCancel={vi.fn()} />);
  act(() => {
    ref.current!.setField("day_pattern", "custom");
    ref.current!.setField("custom_days", ["MON", "fri"]);
    ref.current!.setField("start_type", "sunrise");
    ref.current!.setField("start_sun_offset", 15);
    ref.current!.setField("end_type", "sunset");
    ref.current!.setField("end_sun_offset", -15);
  });
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await waitFor(() =>
    expect(submit).toHaveBeenCalledWith(
      expect.objectContaining({
        day_pattern: "custom",
        custom_days: ["monday", "friday"],
        start_type: "sunrise",
        start_sun_offset: 15,
        end_type: "sunset",
        end_sun_offset: -15,
      }),
    ),
  );
});

describe("compact layout (BB-C-5)", () => {
  it("forwards layout='compact' to the kit form with the app's labels", () => {
    render(
      <ScheduleEntryAdapter
        layout="compact"
        schedule={{ ...schedule, enabled: false }}
        pages={pages}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    expect(document.querySelector("form")).toHaveAttribute("data-layout", "compact");
    expect(screen.getByText("to")).toBeInTheDocument();
    // The entry is off, so More options opens by itself; closed, it names what it holds.
    fireEvent.click(screen.getByRole("button", { name: /More options/ }));
    expect(screen.getByText(/Entry is off/)).toBeInTheDocument();
  });
  it("names a sun start with the app's translated label", () => {
    render(
      <ScheduleEntryAdapter
        layout="compact"
        schedule={{ ...schedule, start_type: "sunset", end_type: "sunrise" }}
        pages={pages}
        onSubmit={vi.fn()}
        onCancel={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /More options/ }));
    expect(screen.getByText(/Starts at sunset/)).toBeInTheDocument();
    expect(screen.getByText(/Ends at sunrise/)).toBeInTheDocument();
  });
  it("keeps the default layout when no layout is given", () => {
    render(<ScheduleEntryAdapter schedule={schedule} pages={pages} onSubmit={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByText("More options")).not.toBeInTheDocument();
    expect(screen.getByRole("radiogroup", { name: "Start time type" })).toBeInTheDocument();
  });
});
