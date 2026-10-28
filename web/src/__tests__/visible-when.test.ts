/**
 * `ui:visible_when` runs the same vectors as Python
 * (`tests/test_settings_ui_grammar.py`), so the field the server validates and
 * the field the form shows are never decided by two different grammars.
 */
import { describe, expect, it } from "vitest";

import { isVisible } from "@/lib/visible-when";
import cases from "@/lib/visible-when.cases.json";

interface Case {
  name: string;
  properties: Record<string, unknown>;
  values: Record<string, unknown>;
  when: unknown;
  visible: boolean;
  context?: Record<string, unknown>;
}

describe("ui:visible_when shared vectors", () => {
  it.each((cases as { cases: Case[] }).cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    expect(isVisible(c.when, c.values, c.properties, c.context)).toBe(c.visible);
  });
});

describe("isVisible", () => {
  it("shows a field with no condition", () => {
    expect(isVisible(undefined, {})).toBe(true);
  });
});
