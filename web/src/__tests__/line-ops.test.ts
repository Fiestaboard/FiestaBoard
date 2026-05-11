import { describe, it, expect } from "vitest";
import { applyLineOpInPlace, applyPatchToSnapshot } from "@/lib/line-ops";
import type { LineAlignment } from "@/lib/api";

describe("applyLineOpInPlace", () => {
  function makeArrays(lines: string[]) {
    return {
      template: [...lines],
      alignments: lines.map(() => "left" as LineAlignment),
      wraps: lines.map(() => false),
    };
  }

  describe("replace_line", () => {
    it("replaces text at valid index", () => {
      const a = makeArrays(["hello", "world"]);
      applyLineOpInPlace({ type: "replace_line", index: 0, text: "hi" }, a.template, a.alignments, a.wraps);
      expect(a.template[0]).toBe("hi");
      expect(a.template[1]).toBe("world");
    });

    it("sets alignment when provided", () => {
      const a = makeArrays(["x"]);
      applyLineOpInPlace({ type: "replace_line", index: 0, text: "x", alignment: "right" }, a.template, a.alignments, a.wraps);
      expect(a.alignments[0]).toBe("right");
    });

    it("sets wrap when provided", () => {
      const a = makeArrays(["x"]);
      applyLineOpInPlace({ type: "replace_line", index: 0, text: "x", wrap: true }, a.template, a.alignments, a.wraps);
      expect(a.wraps[0]).toBe(true);
    });

    it("is a no-op when index is out of range (high)", () => {
      const a = makeArrays(["a"]);
      applyLineOpInPlace({ type: "replace_line", index: 5, text: "z" }, a.template, a.alignments, a.wraps);
      expect(a.template).toEqual(["a"]);
    });

    it("is a no-op when index is negative", () => {
      const a = makeArrays(["a"]);
      applyLineOpInPlace({ type: "replace_line", index: -1, text: "z" }, a.template, a.alignments, a.wraps);
      expect(a.template).toEqual(["a"]);
    });
  });

  describe("insert_line", () => {
    it("inserts at the specified index", () => {
      const a = makeArrays(["a", "b"]);
      applyLineOpInPlace({ type: "insert_line", index: 1, text: "x" }, a.template, a.alignments, a.wraps);
      expect(a.template).toEqual(["a", "x", "b"]);
    });

    it("inserts at the beginning when index is 0", () => {
      const a = makeArrays(["a", "b"]);
      applyLineOpInPlace({ type: "insert_line", index: 0, text: "first" }, a.template, a.alignments, a.wraps);
      expect(a.template[0]).toBe("first");
    });

    it("appends when index equals length", () => {
      const a = makeArrays(["a"]);
      applyLineOpInPlace({ type: "insert_line", index: 1, text: "b" }, a.template, a.alignments, a.wraps);
      expect(a.template).toEqual(["a", "b"]);
    });

    it("clamps negative index to 0", () => {
      const a = makeArrays(["a"]);
      applyLineOpInPlace({ type: "insert_line", index: -10, text: "x" }, a.template, a.alignments, a.wraps);
      expect(a.template[0]).toBe("x");
    });

    it("inserts with default alignment and wrap", () => {
      const a = makeArrays(["a"]);
      applyLineOpInPlace({ type: "insert_line", index: 0, text: "x" }, a.template, a.alignments, a.wraps);
      expect(a.alignments[0]).toBe("left");
      expect(a.wraps[0]).toBe(false);
    });

    it("respects provided alignment and wrap", () => {
      const a = makeArrays(["a"]);
      applyLineOpInPlace({ type: "insert_line", index: 0, text: "x", alignment: "center", wrap: true }, a.template, a.alignments, a.wraps);
      expect(a.alignments[0]).toBe("center");
      expect(a.wraps[0]).toBe(true);
    });
  });

  describe("delete_line", () => {
    it("removes the line at the specified index", () => {
      const a = makeArrays(["a", "b", "c"]);
      applyLineOpInPlace({ type: "delete_line", index: 1 }, a.template, a.alignments, a.wraps);
      expect(a.template).toEqual(["a", "c"]);
    });

    it("removes corresponding alignment and wrap entries", () => {
      const a = makeArrays(["a", "b"]);
      a.alignments[1] = "right";
      a.wraps[1] = true;
      applyLineOpInPlace({ type: "delete_line", index: 0 }, a.template, a.alignments, a.wraps);
      expect(a.alignments).toEqual(["right"]);
      expect(a.wraps).toEqual([true]);
    });

    it("is a no-op when index is out of range (high)", () => {
      const a = makeArrays(["a"]);
      applyLineOpInPlace({ type: "delete_line", index: 10 }, a.template, a.alignments, a.wraps);
      expect(a.template).toEqual(["a"]);
    });

    it("is a no-op when index is negative", () => {
      const a = makeArrays(["a"]);
      applyLineOpInPlace({ type: "delete_line", index: -1 }, a.template, a.alignments, a.wraps);
      expect(a.template).toEqual(["a"]);
    });
  });

  describe("update_line_metadata", () => {
    it("updates alignment at valid index", () => {
      const a = makeArrays(["x"]);
      applyLineOpInPlace({ type: "update_line_metadata", index: 0, alignment: "center" }, a.template, a.alignments, a.wraps);
      expect(a.alignments[0]).toBe("center");
    });

    it("updates wrap at valid index", () => {
      const a = makeArrays(["x"]);
      applyLineOpInPlace({ type: "update_line_metadata", index: 0, wrap: true }, a.template, a.alignments, a.wraps);
      expect(a.wraps[0]).toBe(true);
    });

    it("is a no-op when index is out of range", () => {
      const a = makeArrays(["x"]);
      applyLineOpInPlace({ type: "update_line_metadata", index: 5, alignment: "right" }, a.template, a.alignments, a.wraps);
      expect(a.alignments[0]).toBe("left");
    });
  });
});

describe("applyPatchToSnapshot", () => {
  const baseTemplate = ["hello", "world"];
  const baseMeta = [
    { alignment: "left" as LineAlignment, wrap: false },
    { alignment: "left" as LineAlignment, wrap: false },
  ];

  it("applies a replace_line op", () => {
    const result = applyPatchToSnapshot(
      [{ type: "replace_line", index: 0, text: "hi" }],
      baseTemplate,
      baseMeta,
    );
    expect(result.template[0]).toBe("hi");
    expect(result.template[1]).toBe("world");
  });

  it("does not mutate the input template", () => {
    const t = ["a", "b"];
    applyPatchToSnapshot([{ type: "replace_line", index: 0, text: "x" }], t, baseMeta);
    expect(t[0]).toBe("a");
  });

  it("applies multiple ops in sequence", () => {
    const result = applyPatchToSnapshot(
      [
        { type: "insert_line", index: 0, text: "new" },
        { type: "delete_line", index: 2 },
      ],
      baseTemplate,
      baseMeta,
    );
    expect(result.template).toEqual(["new", "hello"]);
  });

  it("returns updated line_metadata", () => {
    const result = applyPatchToSnapshot(
      [{ type: "replace_line", index: 0, text: "hi", alignment: "right", wrap: true }],
      baseTemplate,
      baseMeta,
    );
    expect(result.line_metadata[0].alignment).toBe("right");
    expect(result.line_metadata[0].wrap).toBe(true);
  });

  it("handles empty changes array", () => {
    const result = applyPatchToSnapshot([], baseTemplate, baseMeta);
    expect(result.template).toEqual(baseTemplate);
  });
});
