import { describe, expect, it } from "vitest";

import type { FormulaDiagnostic, RenderDiagnostics } from "@/lib/api/formula-debug";
import {
  atomState,
  atomValue,
  buildHintIndex,
  errorTag,
  findFormula,
  findLine,
  readsAnyRoot,
} from "@/lib/formula-ide/hints";

function formula(partial: Partial<FormulaDiagnostic>): FormulaDiagnostic {
  return {
    line: 1,
    start: 0,
    end: 10,
    source: "1 + 1",
    value: "2",
    error: null,
    error_at: null,
    message: null,
    ...partial,
  };
}

const foreachLine = {
  line: 2,
  first_row: 2,
  rows_wanted: 7,
  rows_shown: 3,
  clip: "stopped_by_line" as const,
  clip_line: 5,
  widest: 10,
  cut: false,
  hidden: ["J  15M"],
};

describe("errorTag", () => {
  it("is null without an error", () => {
    expect(errorTag(formula({}))).toBeNull();
  });
  it("adds the offset to #SYNTAX", () => {
    expect(errorTag(formula({ error: "#SYNTAX", error_at: 7 }))).toBe("#SYNTAX:7");
  });
  it("keeps other codes verbatim", () => {
    expect(errorTag(formula({ error: "#REF" }))).toBe("#REF");
  });
});

describe("atomValue", () => {
  it("reports rows shown of rows wanted for a FOREACH line", () => {
    const value = atomValue(formula({ line: 2, value: "J  DUE\n14  7M\n49 12M" }), foreachLine);
    expect(value).toEqual({ kind: "rows", shown: 3, wanted: 7 });
  });
  it("shows the first row of a single-row value", () => {
    expect(atomValue(formula({ value: "7:40 AM" }))).toEqual({ kind: "value", text: "7:40 AM" });
  });
  it("shortens a long value", () => {
    const value = atomValue(formula({ value: "A VERY LONG VALUE THAT GOES ON" }));
    expect(value).toEqual({ kind: "value", text: "A VERY LONG VALUE…" });
  });
  it("shows an empty value as empty quotes", () => {
    expect(atomValue(formula({ value: "" }))).toEqual({ kind: "value", text: '""' });
  });
  it("shows the error tag instead of the value", () => {
    expect(atomValue(formula({ error: "#REF", value: "#REF" }))).toEqual({ kind: "error", tag: "#REF" });
  });
});

describe("atomState", () => {
  it("is error when the formula failed", () => {
    expect(atomState(formula({ error: "#DIV/0" }))).toBe("error");
  });
  it("is fallback when DEFAULT caught a missing root", () => {
    const f = formula({ source: 'DEFAULT(weather.temp, "--")', value: "--" });
    expect(atomState(f, ["weather"])).toBe("fallback");
  });
  it("is ok when the fallback reads no missing root", () => {
    const f = formula({ source: 'DEFAULT(weather.temp, "--")', value: "72" });
    expect(atomState(f, ["muni"])).toBe("ok");
  });
});

describe("readsAnyRoot", () => {
  it("matches a root path and an instance path", () => {
    expect(readsAnyRoot("weather.temp + 1", ["weather"])).toBe(true);
    expect(readsAnyRoot("weather:home.temp", ["weather"])).toBe(true);
  });
  it("ignores a root that only appears inside another path", () => {
    expect(readsAnyRoot("item.weather.temp", ["weather"])).toBe(false);
    expect(readsAnyRoot("myweather.temp", ["weather"])).toBe(false);
  });
});

describe("buildHintIndex", () => {
  const diagnostics: RenderDiagnostics = {
    formulas: [
      formula({ line: 1, start: 4, source: ' FORMATDATE(NOW(), "hh:mm AP") ', value: "7:40 AM" }),
      formula({ line: 2, start: 0, source: "FOREACH(x, item)", value: "A\nB\nC" }),
      formula({ line: 6, start: 0, source: "FOREACH(x, item)", value: "A\nB\nC" }),
    ],
    lines: [foreachLine],
  };
  it("keys hints by trimmed source and keeps the first location", () => {
    const index = buildHintIndex(diagnostics);
    expect(index.get('FORMATDATE(NOW(), "hh:mm AP")')).toMatchObject({ line: 1, start: 4, state: "ok" });
    expect(index.get("FOREACH(x, item)")).toMatchObject({ line: 2, value: { kind: "rows", shown: 3, wanted: 7 } });
  });
  it("is empty without diagnostics", () => {
    expect(buildHintIndex(null).size).toBe(0);
  });
  it("finds a formula and its line", () => {
    expect(findFormula(diagnostics, "  FOREACH(x, item) ")?.line).toBe(2);
    expect(findLine(diagnostics, 2)?.rows_wanted).toBe(7);
    expect(findLine(diagnostics, 9)).toBeUndefined();
  });
});
