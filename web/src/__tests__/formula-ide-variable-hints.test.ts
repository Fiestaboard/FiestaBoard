import { describe, expect, it } from "vitest";

import { buildHintIndex, templateVariablePaths, variableProbeTemplate } from "@/lib/formula-ide/hints";

describe("variable value hints (BB-FP-11)", () => {
  it("finds each variable path once, skipping formulas, colours and formatting", () => {
    expect(
      templateVariablePaths([
        "{{weather.temperature}} {{red}} {{= UPPER(date_time.day_of_week) }}",
        "{{weather.temperature|pad:3}} {{home_assistant:den.light.state}} {{fill_space}}",
      ]),
    ).toEqual(["weather.temperature", "home_assistant:den.light.state"]);
  });

  it("probes every path as a formula on one line, so the hint index keys by path", () => {
    const template = variableProbeTemplate(["weather.temperature", "date_time.day_of_week"]);
    expect(template).toEqual(["{{= weather.temperature }} {{= date_time.day_of_week }}"]);
    const index = buildHintIndex({
      formulas: [
        {
          line: 1,
          start: 0,
          end: 26,
          source: " weather.temperature ",
          value: "62",
          error: null,
          error_at: null,
          message: null,
        },
      ],
      lines: null,
    });
    expect(index.get("weather.temperature")?.value).toEqual({ kind: "value", text: "62" });
  });
});
