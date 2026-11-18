import { describe, expect, it } from "vitest";

import { buildRecipe, columnBudget, type ListColumn, listColumnExpr } from "@/lib/formula-ide/recipes";

const columns: ListColumn[] = [
  { field: "time", label: "Time", format: "hh:mm", upper: false, width: 5, cut: "pad" },
  { field: "who", label: "Who", upper: true, width: 4, cut: "pad" },
  { field: "title", label: "Title", upper: true, width: 9, cut: "left" },
];

describe("listColumnExpr", () => {
  it("formats a date column", () => {
    expect(listColumnExpr(columns[0])).toBe('FORMATDATE(DATE(item.time), "hh:mm")');
  });
  it("pads an uppercased column", () => {
    expect(listColumnExpr(columns[1])).toBe("PAD(UPPER(item.who), 4)");
  });
  it("cuts a column with LEFT", () => {
    expect(listColumnExpr(columns[2])).toBe("LEFT(UPPER(item.title), 9)");
  });
  it("leaves a plain column alone", () => {
    expect(listColumnExpr({ field: "x", label: "X", upper: false, width: 3, cut: "none" })).toBe("item.x");
  });
});

describe("columnBudget", () => {
  it("sums columns and the spaces between them against the board", () => {
    expect(columnBudget(columns, 22)).toEqual({ widths: [5, 4, 9], spaces: 2, total: 20, fits: true });
  });
  it("does not fit past the board width", () => {
    expect(columnBudget(columns, 15).fits).toBe(false);
  });
});

describe("buildRecipe", () => {
  it("writes the list recipe with an empty fallback (04c 118:5246)", () => {
    expect(buildRecipe({ recipe: "list", list: "cal.events", take: 3, columns, empty: "NOTHING ELSE TODAY" })).toBe(
      'IF(COUNT(cal.events) = 0, "NOTHING ELSE TODAY", FOREACH(SLICE(cal.events, 0, 3), ' +
        'FORMATDATE(DATE(item.time), "hh:mm") & " " & PAD(UPPER(item.who), 4) & " " & LEFT(UPPER(item.title), 9)))',
    );
  });
  it("writes one thing or another", () => {
    expect(buildRecipe({ recipe: "either", condition: "weather.temp > 80", then: "HOT", otherwise: "NICE" })).toBe(
      'IF(weather.temp > 80, "HOT", "NICE")',
    );
  });
  it("writes a fallback", () => {
    expect(buildRecipe({ recipe: "fallback", value: "weather.temp", fallback: "--" })).toBe(
      'DEFAULT(weather.temp, "--")',
    );
  });
  it("writes a colour by threshold", () => {
    expect(
      buildRecipe({ recipe: "threshold", value: "weather.temp", threshold: 80, above: "red", below: "blue" }),
    ).toBe('IF(weather.temp > 80, COLOR("red"), COLOR("blue"))');
  });
  it("writes a countdown", () => {
    expect(buildRecipe({ recipe: "countdown", value: "cal.next_start", unit: "minutes", suffix: "MIN" })).toBe(
      'DATEDIFF(NOW(), DATE(cal.next_start), "minutes") & " MIN"',
    );
  });
  it("writes a date format, NOW() when no value is chosen", () => {
    expect(buildRecipe({ recipe: "date", value: "", pattern: "ddd MMM DD" })).toBe('FORMATDATE(NOW(), "ddd MMM DD")');
  });
  it("strips quotes a literal cannot hold", () => {
    expect(buildRecipe({ recipe: "fallback", value: "x", fallback: 'say "hi"' })).toBe('DEFAULT(x, "say hi")');
  });
  it("writes nothing for an incomplete form", () => {
    expect(buildRecipe({ recipe: "list", list: "", take: 3, columns, empty: "" })).toBe("");
    expect(buildRecipe({ recipe: "either", condition: " ", then: "a", otherwise: "b" })).toBe("");
  });
});
