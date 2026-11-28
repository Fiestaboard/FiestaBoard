import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { FormulaInspectorPane } from "@/components/formula-ide/formula-inspector-pane";
import { InspectSheet } from "@/components/formula-ide/inspect-sheet";
import { LineProducesCard } from "@/components/formula-ide/line-produces-card";
import { MissingValuesCard, PreviewCaption } from "@/components/formula-ide/missing-values-card";
import {
  PreviewDataControls,
  type PreviewDataView,
  PreviewHeaderControls,
  type PreviewZoom,
} from "@/components/formula-ide/preview-data-controls";
import type { WorkbenchProps } from "@/components/formula-ide/workbench-types";
import type { FormulaDiagnostic, FormulaTrace, LineDiagnostic, RenderDiagnostics } from "@/lib/api/formula-debug";
import { OPEN_PROBLEMS_EVENT } from "@/lib/ide/open-problems";

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

const ifFormula: FormulaDiagnostic = {
  line: 3,
  start: 0,
  end: 43,
  source: 'IF(weather.temp > 80, "HOT", "NICE")',
  value: "NICE",
  error: null,
  error_at: null,
  message: null,
};
const trace: FormulaTrace = {
  ...ifFormula,
  truncated: false,
  events: [
    {
      id: 0,
      parent: null,
      kind: "call",
      label: "IF",
      start: 0,
      end: 36,
      value: '"NICE"',
      value_truncated: false,
      error: null,
    },
    {
      id: 1,
      parent: 0,
      kind: "binary",
      label: ">",
      start: 3,
      end: 20,
      value: "false",
      value_truncated: false,
      error: null,
    },
    {
      id: 2,
      parent: 1,
      kind: "variable",
      label: "weather.temp",
      start: 3,
      end: 15,
      value: "72",
      value_truncated: false,
      error: null,
    },
  ],
};
const fitsLine: LineDiagnostic = {
  line: 3,
  first_row: 3,
  rows_wanted: 1,
  rows_shown: 1,
  clip: null,
  clip_line: null,
  widest: 8,
  cut: false,
  hidden: [],
};

function dataView(overrides: Partial<PreviewDataView> = {}): PreviewDataView {
  return {
    mode: "live",
    onModeChange: vi.fn(),
    atTime: "",
    onAtTimeChange: vi.fn(),
    inspect: false,
    onInspectChange: vi.fn(),
    ...overrides,
  };
}
const fitZoom = (overrides: Partial<PreviewZoom> = {}): PreviewZoom => ({
  mode: "fit",
  onModeChange: vi.fn(),
  ...overrides,
});

async function openView() {
  await userEvent.click(screen.getByRole("button", { name: "View" }));
  return screen.findByRole("menu");
}

describe("PreviewHeaderControls (UX-4-1, DD-W156)", () => {
  it("switches the preview data source as a radio group", async () => {
    const data = dataView();
    wrap(<PreviewHeaderControls data={data} zoom={fitZoom()} size="default" />);
    const group = screen.getByRole("radiogroup", { name: "Preview data" });
    await userEvent.click(within(group).getByRole("radio", { name: "Missing" }));
    expect(data.onModeChange).toHaveBeenCalledWith("missing");
  });

  it("keeps only the data modes and ⋯ View in the row: no Inspect, clock or zoom buttons", () => {
    wrap(<PreviewHeaderControls data={dataView()} zoom={fitZoom()} size="default" />);
    expect(screen.queryByRole("button", { name: /Inspect/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Preview formulas at a time/ })).toBeNull();
    expect(screen.queryByRole("group", { name: "Preview size" })).toBeNull();
    expect(screen.getByRole("button", { name: "View" })).toBeInTheDocument();
  });

  it("lists Preview at a time…, Inspect (I), Fit (F), Actual size (1) in View", async () => {
    wrap(<PreviewHeaderControls data={dataView()} zoom={fitZoom()} size="default" />);
    const menu = await openView();
    expect(within(menu).getByRole("menuitem", { name: "Preview at a time…" })).toBeInTheDocument();
    expect(within(menu).getByRole("menuitemcheckbox", { name: /Inspect/ })).toHaveTextContent("I");
    expect(within(menu).getByRole("menuitemradio", { name: /Fit/ })).toHaveAttribute("aria-checked", "true");
    expect(within(menu).getByRole("menuitemradio", { name: /Actual size/ })).toHaveTextContent("1");
    expect(within(menu).queryByRole("menuitemradio", { name: "Tile md" })).toBeNull();
    expect(within(menu).queryByRole("menuitemcheckbox", { name: "Ruler" })).toBeNull();
  });

  it("turns Inspect on from the View menu", async () => {
    const data = dataView();
    wrap(<PreviewHeaderControls data={data} zoom={fitZoom()} size="default" />);
    const menu = await openView();
    await userEvent.click(within(menu).getByRole("menuitemcheckbox", { name: /Inspect/ }));
    expect(data.onInspectChange).toHaveBeenCalledWith(true);
  });

  it("offers tile sizes and the ruler on a big board", async () => {
    const zoom = fitZoom({ tile: "sm", onTileChange: vi.fn() });
    const ruler = { on: false, onChange: vi.fn() };
    wrap(<PreviewHeaderControls data={dataView()} zoom={zoom} ruler={ruler} size="default" />);
    let menu = await openView();
    await userEvent.click(within(menu).getByRole("menuitemradio", { name: "Tile md" }));
    expect(zoom.onTileChange).toHaveBeenCalledWith("md");
    menu = await openView();
    await userEvent.click(within(menu).getByRole("menuitemcheckbox", { name: "Ruler" }));
    expect(ruler.onChange).toHaveBeenCalledWith(true);
  });

  it("binds F (Fit / Actual size) and 1 (Actual size) outside text", async () => {
    const zoom = fitZoom();
    const { rerender } = wrap(<PreviewHeaderControls data={dataView()} zoom={zoom} size="default" />);
    await userEvent.keyboard("1");
    expect(zoom.onModeChange).toHaveBeenLastCalledWith("actual");
    await userEvent.keyboard("f");
    expect(zoom.onModeChange).toHaveBeenLastCalledWith("actual");
    const actual = fitZoom({ mode: "actual" });
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <PreviewHeaderControls data={dataView()} zoom={actual} size="default" />
      </QueryClientProvider>,
    );
    await userEvent.keyboard("f");
    expect(actual.onModeChange).toHaveBeenLastCalledWith("fit");
  });

  it("leaves F and 1 to a typed field", async () => {
    const zoom = fitZoom();
    wrap(
      <>
        <input aria-label="name" />
        <PreviewHeaderControls data={dataView()} zoom={zoom} size="default" />
      </>,
    );
    await userEvent.type(screen.getByRole("textbox", { name: "name" }), "f1");
    expect(zoom.onModeChange).not.toHaveBeenCalled();
  });

  it("shows the At chip only once a time is set, and resets it to now", async () => {
    const data = dataView({ atTime: "07:00" });
    const { rerender } = wrap(<PreviewHeaderControls data={dataView()} zoom={fitZoom()} size="default" />);
    expect(screen.queryByTestId("preview-time-chip")).toBeNull();
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <PreviewHeaderControls data={data} zoom={fitZoom()} size="default" />
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("preview-time-chip")).toHaveTextContent(/^At.*7:00 AM$/);
    await userEvent.click(screen.getByRole("button", { name: "Preview at the current time" }));
    expect(data.onAtTimeChange).toHaveBeenCalledWith("");
    await waitFor(() => expect(screen.getByRole("button", { name: "View" })).toHaveFocus());
  });

  // OPUS-2651: closing the picker without a time unmounted the focused trigger.
  it("returns focus to View when Preview at a time… closes without a time", async () => {
    wrap(<PreviewHeaderControls data={dataView()} zoom={fitZoom()} size="default" />);
    const menu = await openView();
    await userEvent.click(within(menu).getByRole("menuitem", { name: "Preview at a time…" }));
    expect(await screen.findByTestId("preview-time-chip")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByTestId("preview-time-chip")).toBeNull());
    await waitFor(() => expect(screen.getByRole("button", { name: "View" })).toHaveFocus());
  });

  it("leaves Shift+F alone", async () => {
    const zoom = fitZoom();
    wrap(<PreviewHeaderControls data={dataView()} zoom={zoom} size="default" />);
    await userEvent.keyboard("{Shift>}F{/Shift}");
    expect(zoom.onModeChange).not.toHaveBeenCalled();
  });

  it("is the plain Fit / Actual size toggle on the dock and without the IDE", () => {
    wrap(<PreviewHeaderControls data={null} zoom={fitZoom()} size="touch" />);
    expect(screen.getByRole("group", { name: "Preview size" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "View" })).toBeNull();
  });
});

describe("PreviewDataControls (the dock's More, UX-10-2)", () => {
  it("switches the data source and resets a chosen time", async () => {
    const data = dataView({ atTime: "07:00" });
    wrap(<PreviewDataControls data={data} />);
    await userEvent.click(screen.getByRole("radio", { name: "Sample" }));
    expect(data.onModeChange).toHaveBeenCalledWith("sample");
    await userEvent.click(screen.getByRole("button", { name: "Preview at the current time" }));
    expect(data.onAtTimeChange).toHaveBeenCalledWith("");
  });
});

describe("PreviewCaption (UX-4-4)", () => {
  const caption = { reserved: true, inspecting: false, mode: "live" as const, atLabel: null, unsampled: [] };
  it("keeps its one line on desktop even when it has nothing to say", () => {
    wrap(<PreviewCaption {...caption} />);
    const slot = document.querySelector('[data-slot="preview-caption"]');
    expect(slot).not.toBeNull();
    expect(slot).toHaveClass("h-4", "truncate");
    expect(slot).toBeEmptyDOMElement();
  });
  it("renders nothing on the dock when empty", () => {
    wrap(<PreviewCaption {...caption} reserved={false} />);
    expect(document.querySelector('[data-slot="preview-caption"]')).toBeNull();
  });
  it("says how to Inspect, and that Esc leaves it", () => {
    wrap(<PreviewCaption {...caption} inspecting mode="sample" />);
    expect(screen.getByTestId("inspect-hint")).toHaveTextContent(/click a tile.*Esc to leave/);
  });
  it("names integrations without example values in Sample", () => {
    wrap(<PreviewCaption {...caption} mode="sample" unsampled={["muni"]} />);
    expect(screen.getByTestId("sample-note")).toHaveTextContent("No example values for muni");
  });
  it("explains the render-at clock in Live", () => {
    wrap(<PreviewCaption {...caption} atLabel="7:00 AM" />);
    expect(screen.getByTestId("render-at-note")).toHaveTextContent(
      "“At 7:00 AM” evaluates formulas as if it were 7:00 AM",
    );
  });
});

describe("MissingValuesCard", () => {
  const base = {
    template: ["GOOD MORNING", "{{weather.temp}}°", '{{= IF(weather.temp > 80, "HOT", "NICE") }} OUT'],
    roots: ["weather"],
    formulas: [{ ...ifFormula, error: "#REF", value: "#REF" }],
    sources: { weather: { state: "none" as const, updated_at: null } },
    loading: false,
    failed: false,
  };
  it("lists each missing value with where it shows ??? and #REF", () => {
    wrap(<MissingValuesCard {...base} mode="missing" onAddFallback={vi.fn()} />);
    const card = screen.getByTestId("missing-values");
    expect(within(card).getByText("1 missing")).toBeInTheDocument();
    expect(card).toHaveTextContent(
      "weather.temp — has no data right now → line 2 shows ??? → line 3 can't decide → #REF",
    );
    expect(card).toHaveTextContent('Tip: DEFAULT(weather.temp, "--") shows -- instead of ???');
  });
  it("keeps the heading outline: its titles are level 2 under the editor's h1", () => {
    const { unmount } = wrap(<MissingValuesCard {...base} mode="missing" onAddFallback={vi.fn()} />);
    expect(screen.getAllByRole("heading", { level: 2 }).length).toBeGreaterThan(0);
    expect(screen.queryAllByRole("heading", { level: 5 })).toHaveLength(0);
    unmount();
    wrap(<MissingValuesCard {...base} roots={[]} formulas={[]} mode="missing" onAddFallback={vi.fn()} />);
    expect(screen.getAllByRole("heading", { level: 2 }).length).toBeGreaterThan(0);
  });

  it("adds a DEFAULT fallback to the first ??? line", async () => {
    const onAddFallback = vi.fn();
    wrap(<MissingValuesCard {...base} mode="missing" onAddFallback={onAddFallback} />);
    await userEvent.click(screen.getByRole("button", { name: "Add a fallback on line 2" }));
    expect(onAddFallback).toHaveBeenCalledWith(2, "weather.temp");
  });
  it("says nothing is missing when the page reads no integration", () => {
    wrap(<MissingValuesCard {...base} roots={[]} formulas={[]} mode="missing" onAddFallback={vi.fn()} />);
    expect(screen.getByText("Nothing missing")).toBeInTheDocument();
  });
  // UX-4-4: Pizza showed "Nothing missing" over a #REF on its board.
  it("names a formula error as one, not as nothing missing, and links to Problems", async () => {
    const opened = vi.fn();
    window.addEventListener(OPEN_PROBLEMS_EVENT, opened);
    wrap(<MissingValuesCard {...base} roots={[]} sources={{}} mode="missing" onAddFallback={vi.fn()} />);
    const card = screen.getByTestId("missing-values");
    expect(card).toHaveTextContent("No integration data on this page");
    expect(card).toHaveTextContent("#REF on line 3 is a formula error, not missing data.");
    expect(screen.queryByText("Nothing missing")).toBeNull();
    await userEvent.click(within(card).getByRole("button", { name: "See Problems" }));
    expect(opened).toHaveBeenCalledTimes(1);
    window.removeEventListener(OPEN_PROBLEMS_EVENT, opened);
  });
  it("leaves Live and Sample to the caption slot", () => {
    const { container } = wrap(<MissingValuesCard {...base} mode="sample" onAddFallback={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
  it("reports a failed preview instead of stale data", () => {
    wrap(<MissingValuesCard {...base} failed mode="missing" onAddFallback={vi.fn()} />);
    expect(screen.getByTestId("preview-context-error")).toBeInTheDocument();
  });
});

describe("LineProducesCard", () => {
  it("shows each row a FOREACH line produced and what it hid", () => {
    const line: LineDiagnostic = {
      line: 2,
      first_row: 2,
      rows_wanted: 7,
      rows_shown: 3,
      clip: "stopped_by_line",
      clip_line: 5,
      widest: 10,
      cut: false,
      hidden: ["J  15M", "14  21M"],
    };
    wrap(<LineProducesCard line={line} rendered={["24TH", "J DUE", "14 7M", "49 12M", "62 FOG"]} />);
    const card = screen.getByTestId("line-produces");
    expect(card).toHaveTextContent("Line 2 produces");
    expect(card).toHaveTextContent("row 3");
    expect(card).toHaveTextContent("14 7M");
    expect(card).toHaveTextContent("rows 5–6");
    expect(card).toHaveTextContent("J 15M · 14 21M".replace(/ /g, " "));
    expect(card).toHaveTextContent("3 of 7 rows shown · line 5 stops the list");
  });
});

describe("InspectSheet", () => {
  const diagnostics: RenderDiagnostics = { formulas: [ifFormula], lines: [fitsLine] };
  it("lists the formula's steps with TraceStep and its fit report", () => {
    wrap(
      <InspectSheet
        expression={ifFormula.source}
        formula={ifFormula}
        diagnostics={diagnostics}
        trace={trace}
        loading={false}
        failed={false}
        mode="live"
        atLabel="6:05 PM"
        boardCols={22}
        onClose={vi.fn()}
      />,
    );
    expect(screen.getByRole("heading", { name: "Inspect · line 3" })).toBeInTheDocument();
    const steps = screen.getAllByRole("listitem");
    expect(steps.map((step) => step.textContent)).toEqual([
      expect.stringContaining("weather.temp"),
      expect.stringContaining("weather.temp > 80"),
      expect.stringContaining('IF(weather.temp > 80, "HOT", "NICE")'),
    ]);
    expect(screen.getByText("Steps · Live 6:05 PM")).toBeInTheDocument();
    expect(screen.getByTestId("fit-report")).toHaveTextContent("FitsLine 3 is 8 of 22 columns · nothing cut");
  });
});

function paneProps(overrides: Partial<WorkbenchProps>): WorkbenchProps {
  return {
    open: null,
    setOpen: vi.fn(),
    focus: null,
    setFocus: vi.fn(),
    inspect: true,
    iteration: 0,
    formula: undefined,
    cell: null,
    diagnostics: null,
    rendered: [],
    trace: null,
    traceLoading: false,
    traceFailed: false,
    sourceMapStatus: "complete",
    renderFailed: false,
    boardCols: 22,
    onReplaceFormula: vi.fn(),
    ...overrides,
  };
}

describe("FormulaInspectorPane", () => {
  it("draws no pane before a tile is picked: the caption slot asks for one (UX-4-4)", () => {
    const { container } = wrap(<FormulaInspectorPane {...paneProps({})} />);
    expect(container).toBeEmptyDOMElement();
  });
  it("shows the clicked row, its formula's steps and a one-tap limit", async () => {
    const foreach: FormulaDiagnostic = {
      ...ifFormula,
      line: 2,
      source: "FOREACH(muni.departures, item.route)",
      value: "J\n14\n49",
    };
    const clipped: LineDiagnostic = {
      ...fitsLine,
      line: 2,
      first_row: 2,
      rows_wanted: 7,
      rows_shown: 3,
      clip: "stopped_by_line",
      clip_line: 5,
      hidden: ["J 15M"],
    };
    const onReplaceFormula = vi.fn();
    wrap(
      <FormulaInspectorPane
        {...paneProps({
          focus: { kind: "cell", row: 2, col: 0 },
          formula: foreach,
          cell: {
            origin: { index: 1, source: { line: 2, start: 0, end: 40, kind: "formula" } },
            detail: { formula: foreach, line: clipped, rowInFormula: 2 },
          },
          diagnostics: { formulas: [foreach], lines: [clipped] },
          rendered: ["24TH", "J DUE", "14 7M"],
          trace: {
            ...foreach,
            truncated: false,
            events: [
              {
                id: 0,
                parent: null,
                kind: "call",
                label: "FOREACH",
                start: 0,
                end: 36,
                value: "list(3)",
                value_truncated: false,
                error: null,
              },
            ],
          },
          onReplaceFormula,
        })}
      />,
    );
    expect(screen.getByTestId("inspector-heading")).toHaveTextContent("Row 3 → line 2");
    expect(screen.getByText("Row 3 shows")).toBeInTheDocument();
    expect(screen.getByTestId("trace-steps")).toHaveTextContent("FOREACH(muni.departures, item.route)list(3)");
    expect(screen.getByTestId("clip-report")).toHaveTextContent("3 of 7 rows shown");
    await userEvent.click(screen.getByRole("button", { name: "Limit to 3" }));
    expect(onReplaceFormula).toHaveBeenCalledWith(2, foreach.source, "FOREACH(muni.departures, item.route, 3)");
  });
  it("explains a padding tile", () => {
    wrap(
      <FormulaInspectorPane
        {...paneProps({ focus: { kind: "cell", row: 0, col: 21 }, cell: { origin: null, detail: null } })}
      />,
    );
    expect(screen.getByText(/Row 1, column 22 is layout padding/)).toBeInTheDocument();
  });
  // N13: a failed render (the editor's own preview in Live, or the IDE's in
  // Sample/Missing/at) is why chips have no hints; the pane says so.
  it("says when the render behind the hints failed", () => {
    wrap(<FormulaInspectorPane {...paneProps({ renderFailed: true })} />);
    expect(screen.getByTestId("inspector-render-failed")).toHaveTextContent(/couldn't be rendered/);
  });

  it("says when the page is too large to map", () => {
    wrap(<FormulaInspectorPane {...paneProps({ sourceMapStatus: "limit" })} />);
    expect(screen.getByTestId("inspector-limit")).toBeInTheDocument();
  });
});

// A 1024 px window with the Explorer open leaves the card about 290 px: the
// modes move into View instead of wrapping the header (UX-4-1).
describe("PreviewHeaderControls in a narrow card", () => {
  it("moves Live | Sample | Missing into View when the header is too narrow", async () => {
    const width = vi.spyOn(HTMLElement.prototype, "clientWidth", "get").mockReturnValue(290);
    try {
      const data = dataView();
      wrap(
        <div data-slot="editor-preview-header">
          <PreviewHeaderControls data={data} zoom={fitZoom()} size="default" />
        </div>,
      );
      expect(screen.queryByRole("radiogroup", { name: "Preview data" })).toBeNull();
      const menu = await openView();
      await userEvent.click(within(menu).getByRole("menuitemradio", { name: "Sample" }));
      expect(data.onModeChange).toHaveBeenCalledWith("sample");
    } finally {
      width.mockRestore();
    }
  });
});
