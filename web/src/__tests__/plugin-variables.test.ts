import { describe, expect, it } from "vitest";

import {
  buildVariablesList,
  getVariableGroups,
  groupVariableRows,
  type PluginVariableRow,
  type VariablesBlock,
} from "@/lib/plugin-variables";

describe("buildVariablesList", () => {
  it("returns an empty list when variables are undefined", () => {
    expect(buildVariablesList(undefined, undefined)).toEqual([]);
  });

  it("handles simple variables expressed as a string array (no group)", () => {
    const variables: VariablesBlock = { simple: ["temp_high", "temp_low"] };

    const rows = buildVariablesList(variables, undefined);

    expect(rows).toEqual([
      { name: "temp_high", description: "temp high", maxChars: 22, group: undefined },
      { name: "temp_low", description: "temp low", maxChars: 22, group: undefined },
    ]);
  });

  it("carries the group and description from object-form simple variables", () => {
    const variables: VariablesBlock = {
      groups: { time: { label: "Time" }, date: { label: "Date" } },
      simple: {
        time: { description: "Current time", group: "time", max_length: 5 },
        weekday: { description: "Day of week", group: "date" },
      },
    };

    const rows = buildVariablesList(variables, undefined);

    expect(rows).toEqual([
      { name: "time", description: "Current time", maxChars: 5, group: "time" },
      { name: "weekday", description: "Day of week", maxChars: 22, group: "date" },
    ]);
  });

  it("prefers max_lengths over meta.max_length over the 22 default", () => {
    const variables: VariablesBlock = {
      simple: {
        a: { description: "A", max_length: 10 },
        b: { description: "B", max_length: 10 },
        c: { description: "C" },
      },
    };

    const rows = buildVariablesList(variables, { a: 30 });

    expect(rows.find((r) => r.name === "a")?.maxChars).toBe(30); // from max_lengths
    expect(rows.find((r) => r.name === "b")?.maxChars).toBe(10); // from meta.max_length
    expect(rows.find((r) => r.name === "c")?.maxChars).toBe(22); // default
  });

  it("expands array variables into label + item-field rows without a group", () => {
    const variables: VariablesBlock = {
      arrays: {
        forecast: { label_field: "day", item_fields: ["day", "high", "low"] },
      },
    };

    const rows = buildVariablesList(variables, { "forecast.high": 4 });

    expect(rows).toEqual([
      { name: "forecast.{index}.day", description: "forecast label", maxChars: 22, group: undefined },
      { name: "forecast.{index}.high", description: "forecast high", maxChars: 4, group: undefined },
      { name: "forecast.{index}.low", description: "forecast low", maxChars: 22, group: undefined },
    ]);
  });
});

describe("getVariableGroups", () => {
  it("returns the groups map when present", () => {
    const groups = { time: { label: "Time" } };
    expect(getVariableGroups({ groups })).toEqual(groups);
  });

  it("returns an empty object when groups are absent or variables undefined", () => {
    expect(getVariableGroups({})).toEqual({});
    expect(getVariableGroups(undefined)).toEqual({});
  });
});

describe("groupVariableRows", () => {
  const rows: PluginVariableRow[] = [
    { name: "time", description: "Current time", maxChars: 5, group: "time" },
    { name: "hour", description: "Hour", maxChars: 2, group: "time" },
    { name: "weekday", description: "Weekday", maxChars: 9, group: "date" },
    { name: "raw", description: "Raw", maxChars: 22, group: undefined },
  ];

  it("orders sections by the manifest group order and appends ungrouped under the general label", () => {
    const groups = { date: { label: "Date" }, time: { label: "Time" } };

    const sections = groupVariableRows(rows, groups, "General");

    expect(sections.map((s) => s.label)).toEqual(["Date", "Time", "General"]);
    expect(sections[0].rows.map((r) => r.name)).toEqual(["weekday"]);
    expect(sections[1].rows.map((r) => r.name)).toEqual(["time", "hour"]);
    expect(sections[2]).toMatchObject({ groupId: null, label: "General" });
    expect(sections[2].rows.map((r) => r.name)).toEqual(["raw"]);
  });

  it("skips groups that have no matching variables", () => {
    const groups = { time: { label: "Time" }, empty: { label: "Empty" } };

    const sections = groupVariableRows(rows, groups, "General");

    expect(sections.map((s) => s.label)).not.toContain("Empty");
  });

  it("treats a variable whose group is not defined as ungrouped", () => {
    const orphan: PluginVariableRow[] = [{ name: "x", description: "x", maxChars: 1, group: "missing" }];

    const sections = groupVariableRows(orphan, { time: { label: "Time" } }, "General");

    expect(sections).toEqual([{ groupId: null, label: "General", rows: orphan }]);
  });

  it("puts every row under the general section when no groups are defined", () => {
    const sections = groupVariableRows(rows, {}, "General");

    expect(sections).toHaveLength(1);
    expect(sections[0]).toMatchObject({ groupId: null, label: "General" });
    expect(sections[0].rows).toEqual(rows);
  });

  it("omits the general section when every row belongs to a defined group", () => {
    const grouped: PluginVariableRow[] = [{ name: "time", description: "t", maxChars: 5, group: "time" }];

    const sections = groupVariableRows(grouped, { time: { label: "Time" } }, "General");

    expect(sections.map((s) => s.label)).toEqual(["Time"]);
  });
});
