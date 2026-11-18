import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { FormulaInspectorPane } from "@/components/formula-ide/formula-inspector-pane";
import { InspectSheet } from "@/components/formula-ide/inspect-sheet";
import { LineProducesCard } from "@/components/formula-ide/line-produces-card";
import { MissingValuesCard } from "@/components/formula-ide/missing-values-card";
import { PreviewDataControls } from "@/components/formula-ide/preview-data-controls";
import type { WorkbenchProps } from "@/components/formula-ide/workbench-types";
import type { FormulaDiagnostic, FormulaTrace, LineDiagnostic, RenderDiagnostics } from "@/lib/api/formula-debug";

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

describe("PreviewDataControls", () => {
  it("switches the preview data source as a radio group", async () => {
    const onModeChange = vi.fn();
    wrap(
      <PreviewDataControls mode="live" onModeChange={onModeChange} atTime="" onAtTimeChange={vi.fn()} size="default" />,
    );
    const group = screen.getByRole("radiogroup", { name: "Preview data" });
    await userEvent.click(within(group).getByRole("radio", { name: "Missing" }));
    expect(onModeChange).toHaveBeenCalledWith("missing");
  });
  it("offers Inspect only when the host passes it", async () => {
    const onInspectChange = vi.fn();
    const { rerender } = wrap(
      <PreviewDataControls mode="live" onModeChange={vi.fn()} atTime="" onAtTimeChange={vi.fn()} size="touch" />,
    );
    expect(screen.queryByRole("button", { name: /Inspect/ })).toBeNull();
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <PreviewDataControls
          mode="live"
          onModeChange={vi.fn()}
          atTime=""
          onAtTimeChange={vi.fn()}
          size="default"
          inspect={false}
          onInspectChange={onInspectChange}
        />
      </QueryClientProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: /Inspect/ }));
    expect(onInspectChange).toHaveBeenCalledWith(true);
  });
  it("resets a chosen render time to now", async () => {
    const onAtTimeChange = vi.fn();
    wrap(
      <PreviewDataControls
        mode="live"
        onModeChange={vi.fn()}
        atTime="07:00"
        onAtTimeChange={onAtTimeChange}
        size="default"
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Preview at the current time" }));
    expect(onAtTimeChange).toHaveBeenCalledWith("");
  });
});

describe("MissingValuesCard", () => {
  const base = {
    atLabel: null,
    template: ["GOOD MORNING", "{{weather.temp}}°", '{{= IF(weather.temp > 80, "HOT", "NICE") }} OUT'],
    roots: ["weather"],
    unsampled: [],
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
  it("keeps the heading outline: its titles are level 3 under the editor's h2", () => {
    const { unmount } = wrap(<MissingValuesCard {...base} mode="missing" onAddFallback={vi.fn()} />);
    expect(screen.getAllByRole("heading", { level: 3 }).length).toBeGreaterThan(0);
    expect(screen.queryAllByRole("heading", { level: 5 })).toHaveLength(0);
    unmount();
    wrap(<MissingValuesCard {...base} roots={[]} formulas={[]} mode="missing" onAddFallback={vi.fn()} />);
    expect(screen.getAllByRole("heading", { level: 3 }).length).toBeGreaterThan(0);
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
  it("names integrations without example values in Sample", () => {
    wrap(<MissingValuesCard {...base} unsampled={["muni"]} mode="sample" onAddFallback={vi.fn()} />);
    expect(screen.getByTestId("sample-note")).toHaveTextContent("No example values for muni");
  });
  it("explains the render-at clock in Live", () => {
    wrap(<MissingValuesCard {...base} atLabel="7:00 AM" mode="live" onAddFallback={vi.fn()} />);
    expect(screen.getByTestId("render-at-note")).toHaveTextContent(
      "“At 7:00 AM” evaluates formulas as if it were 7:00 AM",
    );
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
  it("asks for a tile before anything is selected", () => {
    wrap(<FormulaInspectorPane {...paneProps({})} />);
    expect(screen.getByText(/Click a tile on the preview/)).toBeInTheDocument();
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
