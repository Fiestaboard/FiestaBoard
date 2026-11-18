import { describe, expect, it } from "vitest";

import { limitForeach, splitTopLevelArgs } from "@/lib/formula-ide/fixes";

describe("splitTopLevelArgs", () => {
  it("splits on top-level commas only", () => {
    expect(splitTopLevelArgs('a, F(b, c), "x, y"')).toEqual(["a", "F(b, c)", '"x, y"']);
  });
});

describe("limitForeach", () => {
  it("adds a row limit to a two-argument FOREACH", () => {
    expect(limitForeach("FOREACH(muni.departures, item.route)", 3)).toBe("FOREACH(muni.departures, item.route, 3)");
  });
  it("replaces an existing limit", () => {
    expect(limitForeach("FOREACH(x, item, 7)", 3)).toBe("FOREACH(x, item, 3)");
  });
  it("is null when the formula is not a top-level FOREACH", () => {
    expect(limitForeach('IF(COUNT(x) = 0, "", FOREACH(x, item))', 3)).toBeNull();
    expect(limitForeach("FOREACH(x, item) & y", 3)).toBeNull();
  });
});
