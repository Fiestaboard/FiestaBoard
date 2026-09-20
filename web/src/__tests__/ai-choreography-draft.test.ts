import { describe, expect, it } from "vitest";

import { parseToolDraft } from "@/lib/ai-choreography/draft";

describe("parseToolDraft", () => {
  it("reads the tool name as soon as it is complete", () => {
    expect(parseToolDraft('{"op": "create_pa').name).toBeNull();
    expect(parseToolDraft('{"op": "create_page"').name).toBe("create_page");
    expect(parseToolDraft('{"tool": "update_setting", "args": {').name).toBe("update_setting");
  });

  it("keeps complete string args and finished list items, and reports the string in progress", () => {
    const draft = parseToolDraft('{"op": "create_page", "args": {"name": "Morning", "template_lines": ["HELLO", "WOR');
    expect(draft.strings).toEqual({ name: "Morning" });
    expect(draft.lists).toEqual({ template_lines: ["HELLO"] });
    expect(draft.partial).toEqual({ key: "template_lines", index: 1, value: "WOR" });
  });

  it("reports a top-level string in progress", () => {
    const draft = parseToolDraft('{"op": "create_page", "args": {"name": "Morn');
    expect(draft.strings).toEqual({});
    expect(draft.partial).toEqual({ key: "name", value: "Morn" });
  });

  it("skips numbers, booleans and nested objects without losing its place", () => {
    const draft = parseToolDraft(
      '{"op": "update_setting", "args": {"category": "display", "values": {"reduce_motion": true}, "duration_seconds": 30, "name": "X"}}',
    );
    expect(draft.strings).toEqual({ category: "display", name: "X" });
    expect(draft.lists).toEqual({});
    expect(draft.partial).toBeUndefined();
  });

  it("decodes escapes inside strings", () => {
    const draft = parseToolDraft(
      '{"op": "create_page", "args": {"name": "Say \\"hi\\"\\n", "template_lines": ["\\u0041"]}}',
    );
    expect(draft.strings.name).toBe('Say "hi"\n');
    expect(draft.lists.template_lines).toEqual(["A"]);
  });

  it("never throws on garbage", () => {
    for (const text of [
      "",
      "{",
      '{"op"',
      '{"op": 1',
      "not json at all",
      '{"args": [1,2',
      '{"op": "x", "args": {"a": ',
    ]) {
      expect(() => parseToolDraft(text)).not.toThrow();
    }
  });
});
