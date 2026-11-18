import { describe, expect, it } from "vitest";

import type { FormulaDiagnostic } from "@/lib/api/formula-debug";
import {
  atIsoForTime,
  buildPreviewContext,
  fallbackTip,
  missingReport,
  referencedRoots,
  sampleValues,
} from "@/lib/formula-ide/data-source";

const template = [
  "GOOD MORNING",
  "{{weather.temp}}° {{weather.temp_color}}",
  '{{= IF(weather.temp > 80, "HOT", "NICE") }} OUT',
  "N JUDAH {{muni:home.n_judah.next}}",
  "{{= FOREACH(cal.events, item.title) }}",
  "HAVE A GREAT DAY",
];
const pluginIds = ["weather", "muni", "cal", "date_time", "item"];

describe("referencedRoots", () => {
  it("lists the plugins a template reads, in plugin order", () => {
    expect(referencedRoots(template, ["weather", "muni", "cal", "date_time"])).toEqual(["weather", "muni", "cal"]);
  });
  it("does not treat a loop field as a plugin read", () => {
    expect(referencedRoots(["{{= FOREACH(cal.events, item.title) }}"], pluginIds)).toEqual(["cal"]);
  });
  it("is empty for a template without data", () => {
    expect(referencedRoots(["HELLO"], pluginIds)).toEqual([]);
  });
});

describe("sampleValues", () => {
  const metadata = {
    weather: {
      temp: { example: "70" },
      condition: { example: "" },
      temp_color: { type: "color" as const, example: "" },
    },
    cal: { events: { type: "array", example: "Standup" } as never },
    muni: { next: { example: "4 MIN" } },
  };
  it("samples scalar examples of referenced roots only", () => {
    expect(sampleValues(metadata, ["weather", "cal"])).toEqual({
      values: { "weather.temp": "70" },
      unsampled: ["cal"],
    });
  });
  it("caps the number of sampled values at the hub limit", () => {
    const many = Object.fromEntries(Array.from({ length: 70 }, (_, i) => [`f${i}`, { example: "x" }]));
    expect(Object.keys(sampleValues({ big: many }, ["big"]).values)).toHaveLength(64);
  });
});

describe("buildPreviewContext", () => {
  it("is null for live data at the real time (the ordinary render)", () => {
    expect(buildPreviewContext({ mode: "live", roots: ["weather"], sample: {} })).toBeNull();
  });
  it("pins the clock on cached data for live at a chosen time", () => {
    expect(buildPreviewContext({ mode: "live", roots: [], sample: {}, at: "2026-11-17T07:00:00" })).toEqual({
      at: "2026-11-17T07:00:00",
      data: "cached",
    });
  });
  it("sends sample values for sample", () => {
    expect(buildPreviewContext({ mode: "sample", roots: ["weather"], sample: { "weather.temp": "70" } })).toEqual({
      values: { "weather.temp": "70" },
      data: "cached",
    });
  });
  it("marks every referenced root missing for missing", () => {
    expect(buildPreviewContext({ mode: "missing", roots: ["weather", "muni"], sample: {}, at: "x" })).toEqual({
      missing: ["weather", "muni"],
      data: "cached",
      at: "x",
    });
  });
});

describe("atIsoForTime", () => {
  it("builds a naive ISO instant for today in the hub's zone", () => {
    expect(atIsoForTime("07:05", new Date(2026, 10, 17, 18, 0))).toBe("2026-11-17T07:05:00");
  });
  it("rejects a malformed time", () => {
    expect(atIsoForTime("7", new Date())).toBeNull();
  });
});

describe("missingReport", () => {
  const formulas: FormulaDiagnostic[] = [
    {
      line: 3,
      start: 0,
      end: 43,
      source: 'IF(weather.temp > 80, "HOT", "NICE")',
      value: "#REF",
      error: "#REF",
      error_at: null,
      message: "No value at weather.temp",
    },
  ];
  it("lists each missing root with its variable lines, #REF lines and hub freshness", () => {
    const report = missingReport({
      template,
      roots: ["weather", "muni"],
      formulas,
      sources: { weather: { state: "stale", updated_at: "2026-11-17T06:12:00Z" } },
    });
    expect(report).toEqual([
      {
        root: "weather",
        path: "weather.temp",
        state: "stale",
        updatedAt: "2026-11-17T06:12:00Z",
        variableLines: [2],
        formulaLines: [3],
        fallbackLines: [],
      },
      {
        root: "muni",
        path: "muni:home.n_judah.next",
        state: "none",
        updatedAt: null,
        variableLines: [4],
        formulaLines: [],
        fallbackLines: [],
      },
    ]);
  });
  it("names the fallback a DEFAULT produced", () => {
    const report = missingReport({
      template: ['{{= DEFAULT(weather.temp, "--") }}'],
      roots: ["weather"],
      formulas: [{ ...formulas[0], line: 1, source: 'DEFAULT(weather.temp, "--")', value: "--", error: null }],
      sources: null,
    });
    expect(report[0]).toMatchObject({ fallbackLines: [1], formulaLines: [] });
  });
  it("suggests a DEFAULT for the first missing path", () => {
    expect(fallbackTip("weather.temp")).toBe('DEFAULT(weather.temp, "--")');
  });
});
