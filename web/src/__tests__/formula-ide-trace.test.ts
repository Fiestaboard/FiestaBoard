import { describe, expect, it } from "vitest";

import type { CellSourceMap, FormulaTrace, FormulaTraceEvent, RenderDiagnostics } from "@/lib/api/formula-debug";
import { completionContext, matchFunctions } from "@/lib/formula-ide/autocomplete";
import { flattenFormula, iterationCount, lineValueHints, prettyPrint } from "@/lib/formula-ide/pretty";
import { cellOrigin, originDetail, rowsForSource } from "@/lib/formula-ide/source-map";
import { traceSteps } from "@/lib/formula-ide/trace-steps";

function event(
  partial: Partial<FormulaTraceEvent> & Pick<FormulaTraceEvent, "id" | "start" | "end">,
): FormulaTraceEvent {
  return {
    parent: null,
    kind: "call",
    label: "",
    value: "",
    value_truncated: false,
    error: null,
    ...partial,
  };
}

const EXPR = 'IF(a > 1, "X", PAD(b, 4))';

describe("prettyPrint", () => {
  it("indents calls and keeps the source range of every line", () => {
    const { text, lines } = prettyPrint(EXPR);
    expect(text.split("\n")).toEqual(["IF(", "  a > 1,", '  "X",', "  PAD(", "    b,", "    4", "  )", ")"]);
    expect(lines).toEqual([
      { from: 0, to: 3 },
      { from: 3, to: 9 },
      { from: 10, to: 14 },
      { from: 15, to: 19 },
      { from: 19, to: 21 },
      { from: 22, to: 23 },
      { from: 23, to: 24 },
      { from: 24, to: 25 },
    ]);
  });
  it("round-trips through flattenFormula", () => {
    expect(flattenFormula(prettyPrint(EXPR).text)).toBe(EXPR);
  });
  it("keeps commas and parentheses inside strings", () => {
    expect(prettyPrint('JOIN(x, ", (")').text).toBe('JOIN(\n  x,\n  ", ("\n)');
  });
});

describe("lineValueHints", () => {
  const events = [
    event({ id: 0, start: 0, end: 25, value: '"X"' }),
    event({ id: 1, parent: 0, kind: "binary", start: 3, end: 8, value: "true" }),
    event({ id: 2, parent: 1, kind: "variable", start: 3, end: 4, value: "2" }),
    event({ id: 3, parent: 0, kind: "literal", start: 10, end: 13, value: '"X"' }),
  ];
  it("puts the outermost non-literal value starting on each line in the margin", () => {
    const hints = lineValueHints(events, prettyPrint(EXPR).lines, 0);
    expect(hints).toEqual([null, "true", null, null, null, null, null, null]);
  });
  it("shows the error tag of a failed step", () => {
    const failed = [
      event({ id: 0, start: 0, end: 25 }),
      event({ id: 1, parent: 0, start: 15, end: 24, error: "#VALUE" }),
    ];
    expect(lineValueHints(failed, prettyPrint(EXPR).lines, 0)[3]).toBe("#VALUE");
  });
  it("steps through repeated loop evaluations", () => {
    const loop = [
      event({ id: 0, start: 0, end: 25 }),
      event({ id: 1, parent: 0, kind: "binary", start: 3, end: 8, value: "first" }),
      event({ id: 2, parent: 0, kind: "binary", start: 3, end: 8, value: "second" }),
    ];
    expect(iterationCount(loop)).toBe(2);
    expect(lineValueHints(loop, prettyPrint(EXPR).lines, 1)[1]).toBe("second");
    expect(lineValueHints(loop, prettyPrint(EXPR).lines, 9)[1]).toBe("second");
  });
});

const TRACE: FormulaTrace = {
  line: 3,
  start: 0,
  end: 43,
  source: 'IF(weather.temp > 80, "HOT", "NICE")',
  value: "NICE",
  error: null,
  error_at: null,
  message: null,
  truncated: false,
  events: [
    event({ id: 0, start: 0, end: 36, value: '"NICE"' }),
    event({ id: 1, parent: 0, kind: "binary", start: 3, end: 20, value: "false" }),
    event({ id: 2, parent: 1, kind: "variable", start: 3, end: 15, value: "72" }),
    event({ id: 3, parent: 1, kind: "literal", start: 18, end: 20, value: "80" }),
    event({ id: 4, parent: 0, kind: "literal", start: 29, end: 35, value: '"NICE"' }),
  ],
};

describe("traceSteps", () => {
  it("lists executed non-literal steps innermost first with their nesting", () => {
    expect(traceSteps(TRACE, 0)).toEqual([
      { id: 2, expression: "weather.temp", value: "72", state: "ok", depth: 2 },
      { id: 1, expression: "weather.temp > 80", value: "false", state: "ok", depth: 1 },
      { id: 0, expression: 'IF(weather.temp > 80, "HOT", "NICE")', value: '"NICE"', state: "ok", depth: 0 },
    ]);
  });
  it("shows an error step's tag", () => {
    const failed = {
      ...TRACE,
      events: [event({ id: 0, start: 0, end: 15, kind: "variable", error: "#REF", value: "" })],
    };
    expect(traceSteps(failed, 0)[0]).toMatchObject({ state: "error", value: "#REF" });
  });
  it("keeps one loop iteration", () => {
    const loop = {
      ...TRACE,
      events: [
        event({ id: 0, start: 0, end: 36 }),
        event({ id: 1, parent: 0, kind: "binary", start: 3, end: 20, value: "a" }),
        event({ id: 2, parent: 1, kind: "variable", start: 3, end: 15, value: "1" }),
        event({ id: 3, parent: 0, kind: "binary", start: 3, end: 20, value: "b" }),
        event({ id: 4, parent: 3, kind: "variable", start: 3, end: 15, value: "2" }),
      ],
    };
    expect(traceSteps(loop, 1).map((step) => step.value)).toEqual(["2", "b", ""]);
  });
  it("slices spans by code point", () => {
    const emoji = {
      ...TRACE,
      source: '"😀" & x',
      events: [event({ id: 0, kind: "variable", start: 6, end: 7, value: "1" })],
    };
    expect(traceSteps(emoji, 0)[0].expression).toBe("x");
  });
});

describe("source map", () => {
  const map: CellSourceMap = {
    rows: 3,
    cols: 4,
    sources: [
      { line: 1, start: 0, end: 1, kind: "literal" },
      { line: 2, start: 0, end: 30, kind: "formula" },
    ],
    cells: [
      [0, null, null, null],
      [1, 1, null, null],
      [1, 1, 1, null],
    ],
  };
  const diagnostics: RenderDiagnostics = {
    formulas: [
      {
        line: 2,
        start: 0,
        end: 30,
        source: "FOREACH(x, item)",
        value: "AB\nABC",
        error: null,
        error_at: null,
        message: null,
      },
    ],
    lines: [
      {
        line: 2,
        first_row: 2,
        rows_wanted: 7,
        rows_shown: 2,
        clip: "board_end",
        clip_line: null,
        widest: 3,
        cut: false,
        hidden: [],
      },
    ],
  };
  it("finds the authored source of a cell", () => {
    expect(cellOrigin(map, 1, 1)).toEqual({ index: 1, source: map.sources[1] });
    expect(cellOrigin(map, 0, 3)).toBeNull();
    expect(cellOrigin(map, 9, 9)).toBeNull();
  });
  it("lists the board rows a source fills", () => {
    expect(rowsForSource(map, 1)).toEqual([1, 2]);
  });
  it("names the formula and its FOREACH row for a clicked row", () => {
    const detail = originDetail(map.sources[1], diagnostics, 2);
    expect(detail.formula?.source).toBe("FOREACH(x, item)");
    expect(detail.rowInFormula).toBe(2);
    expect(detail.line?.rows_wanted).toBe(7);
  });
});

describe("autocomplete", () => {
  const functions = {
    FORMATDATE: { category: "date", signature: 'FORMATDATE(d, "MMM DD")', summary: "Format" },
    FOREACH: { category: "array", signature: "FOREACH(array, rowExpr[, limit])", summary: "Rows" },
    IF: { category: "logic", signature: "IF(cond, then[, else])", summary: "If" },
  };
  it("completes the word before the caret", () => {
    expect(completionContext("TRUE, FO", 8)).toEqual({ from: 6, word: "FO" });
  });
  it("does not complete inside a string or a variable path", () => {
    expect(completionContext('"FO', 3)).toBeNull();
    expect(completionContext("weather.fo", 10)).toBeNull();
  });
  it("lists only real built-ins with the prefix, by name", () => {
    expect(matchFunctions("fo", functions).map((fn) => fn.name)).toEqual(["FOREACH", "FORMATDATE"]);
    expect(matchFunctions("", functions)).toEqual([]);
  });
});
