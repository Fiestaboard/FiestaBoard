/**
 * BB-FP-15 (Figma 111:30911 "Formula editor · Code") and BB-FP-16 (132:20145
 * Inspect): the docked formula panel and Inspect, detail by detail.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { BoardCellHighlight } from "@/components/formula-ide/board-cell-highlight";
import { FormulaCodeCard } from "@/components/formula-ide/formula-code-card";
import { type FormulaIdeBridge, FormulaIdeContext } from "@/components/formula-ide/formula-ide-context";
import { FormulaInspectorPane } from "@/components/formula-ide/formula-inspector-pane";
import { LineProducesCard } from "@/components/formula-ide/line-produces-card";
import type { OpenFormulaState } from "@/components/formula-ide/use-formula-ide";
import { WorkbenchHeader } from "@/components/formula-ide/workbench-header";
import type { WorkbenchProps } from "@/components/formula-ide/workbench-types";
import { TipTapTemplateEditor } from "@/components/tiptap-template-editor/TipTapTemplateEditor";

vi.mock("@/lib/api", async (importOriginal) => {
  const mod = (await importOriginal()) as Record<string, unknown>;
  return {
    ...mod,
    api: {
      ...(mod.api as Record<string, unknown>),
      getTemplateVariables: vi.fn().mockResolvedValue({ variables: {}, colors: {}, formatting: {} }),
      validateTemplate: vi.fn().mockResolvedValue({ valid: true, errors: [], warnings: [] }),
    },
  };
});

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

const open: OpenFormulaState = {
  key: 1,
  tab: "code",
  draft: null,
  expression: "UPPER(date_time.day_of_week)",
  apply: vi.fn(),
  cancel: vi.fn(),
};

function props(overrides: Partial<WorkbenchProps> = {}): WorkbenchProps {
  return {
    open,
    setOpen: vi.fn(),
    focus: null,
    setFocus: vi.fn(),
    inspect: false,
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

describe("docked formula panel (BB-FP-15)", () => {
  it("switches Code and Builder with a Tabs list, not a filled toggle", async () => {
    const setOpen = vi.fn();
    render(<WorkbenchHeader line={2} tab="code" setOpen={setOpen} />);
    const tabs = screen.getByRole("tablist", { name: "Formula editor mode" });
    expect(screen.getByRole("tab", { name: "Code" })).toHaveAttribute("aria-selected", "true");
    expect(tabs.querySelector("[aria-pressed]")).toBeNull();
    await userEvent.click(screen.getByRole("tab", { name: "Builder" }));
    expect(setOpen).toHaveBeenCalled();
    const next = setOpen.mock.calls[0][0] as (s: OpenFormulaState) => OpenFormulaState;
    expect(next(open).tab).toBe("builder");
  });

  it("draws a 2 px formula-blue border and an iconless Update formula on the right", () => {
    wrap(<FormulaCodeCard {...props()} />);
    expect(screen.getByTestId("formula-code-card")).toHaveClass("border-2", "border-tag-formula");
    const update = screen.getByRole("button", { name: "Update formula" });
    expect(update.querySelector("svg")).toBeNull();
    expect(update.parentElement).toHaveClass("shrink-0");
    expect(update.parentElement?.parentElement).not.toHaveClass("flex-wrap");
  });

  it("sets the gutter and code in the mono stack, not generic monospace", () => {
    wrap(<FormulaCodeCard {...props()} />);
    const css = [...document.querySelectorAll("style")].map((style) => style.textContent ?? "").join("\n");
    expect(css).toMatch(/\.cm-scroller\s*\{[^}]*font-family:\s*var\(--font-mono-stack\)/);
  });

  it("heads the line card in 14 px semibold", () => {
    render(
      <LineProducesCard
        line={{
          line: 1,
          first_row: 1,
          rows_wanted: 1,
          rows_shown: 1,
          clip: null,
          clip_line: null,
          widest: 6,
          cut: false,
          hidden: [],
        }}
        rendered={["FRIDAY"]}
      />,
    );
    expect(screen.getByRole("heading", { name: "Line 1 produces" })).toHaveClass("text-sm");
  });

  it("tints the template line the IDE is about", () => {
    const bridge = { hint: () => undefined, openFormula: () => false, inspectFormula: vi.fn(), activeLine: 2 };
    wrap(
      <FormulaIdeContext.Provider value={bridge as FormulaIdeBridge}>
        <TipTapTemplateEditor value={"A\nB\nC"} onChange={vi.fn()} showToolbar={false} boardLines={6} boardWidth={22} />
      </FormulaIdeContext.Provider>,
    );
    const band = screen.getByTestId("template-active-line");
    expect(band).toHaveClass("bg-tint-selected");
    // Line 2 starts one (24 px) line below the card's 0.75rem padding.
    expect(band.style.top).toMatch(/^calc\((0\.75rem \+ 24px|24px \+ 0\.75rem)\)$/);
  });

  it("draws no band without an active line", () => {
    wrap(<TipTapTemplateEditor value={"A\nB"} onChange={vi.fn()} showToolbar={false} boardLines={6} boardWidth={22} />);
    expect(screen.queryByTestId("template-active-line")).toBeNull();
  });
});

describe("Inspect (BB-FP-16)", () => {
  it("frames the pane with a 2 px amber border", () => {
    wrap(<FormulaInspectorPane {...props({ open: null, inspect: true })} />);
    expect(screen.getByTestId("inspector-pane")).toHaveClass("border-2", "border-ring");
  });

  it("keeps steps full width until the pane itself is wide, so identifiers don't break", () => {
    const formula = {
      line: 3,
      start: 0,
      end: 30,
      source: '"LUNCH: " & random.choice',
      value: "LUNCH: RAMEN",
      error: null,
      error_at: null,
      message: null,
    };
    wrap(
      <FormulaInspectorPane
        {...props({
          open: null,
          inspect: true,
          focus: { kind: "formula", expression: formula.source, iteration: 0 },
          formula,
          diagnostics: { formulas: [formula], lines: [] },
        })}
      />,
    );
    const pane = screen.getByTestId("inspector-pane");
    expect(pane).toHaveClass("@container");
    const columns = pane.querySelector('[class*="grid-cols-"]');
    expect(columns?.className).toContain("@2xl:grid-cols-");
    expect(columns?.className).not.toMatch(/(^|\s)md:grid-cols-/);
  });

  it("draws the cell outline above the board's transformed layer", async () => {
    const cells = [[0, 0]] as const;
    const selected = [0, 0] as const;
    // The board's tiles, as the preview stage holds them.
    const stage = document.createElement("div");
    stage.innerHTML = '<div data-row="0" data-col="0"></div>';
    const mount = document.createElement("div");
    stage.appendChild(mount);
    document.body.appendChild(stage);
    render(<BoardCellHighlight containerRef={{ current: stage }} cells={cells} selected={selected} />, {
      container: mount,
    });
    expect(await screen.findByTestId("inspect-band")).toHaveClass("z-10");
    expect(screen.getByTestId("inspect-band")).not.toHaveClass("border-dashed");
    expect(screen.getByTestId("inspect-cell")).toHaveClass("z-10");
  });
});
