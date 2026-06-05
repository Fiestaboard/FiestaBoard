/**
 * Tests for TipTap template serialization (simplified model: paragraph + hardBreak)
 */
import { describe, expect, it } from "vitest";

import { parseTemplateSimple, serializeTemplateSimple } from "../components/tiptap-template-editor/utils/serialization";

describe("Simple serialization – 3-line mode (Note)", () => {
  describe("parseTemplateSimple with maxLines=3", () => {
    it("creates a doc with exactly 2 hardBreaks for 3 lines", () => {
      const doc = parseTemplateSimple("A\nB\nC", 3);
      const para = doc.content![0];
      const hardBreaks = para.content!.filter((n) => n.type === "hardBreak");
      expect(hardBreaks).toHaveLength(2);
    });

    it("pads single-line input to 3 lines", () => {
      const doc = parseTemplateSimple("ONLY", 3);
      const para = doc.content![0];
      const hardBreaks = para.content!.filter((n) => n.type === "hardBreak");
      expect(hardBreaks).toHaveLength(2);
    });

    it("preserves input beyond 3 lines (no truncation)", () => {
      const doc = parseTemplateSimple("A\nB\nC\nD\nE", 3);
      const para = doc.content![0];
      const hardBreaks = para.content!.filter((n) => n.type === "hardBreak");
      expect(hardBreaks).toHaveLength(4); // 5 lines = 4 hardBreaks
    });

    it("empty string still has 2 hardBreaks", () => {
      const doc = parseTemplateSimple("", 3);
      const para = doc.content![0];
      const hardBreaks = para.content!.filter((n) => n.type === "hardBreak");
      expect(hardBreaks).toHaveLength(2);
    });
  });

  describe("serializeTemplateSimple with maxLines=3", () => {
    it("produces exactly 3 lines", () => {
      const doc = parseTemplateSimple("HELLO\nWORLD\n", 3);
      const serialized = serializeTemplateSimple(doc, 3);
      const lines = serialized.split("\n");
      expect(lines).toHaveLength(3);
    });

    it("pads short content to 3 lines", () => {
      const doc = parseTemplateSimple("HI", 3);
      const serialized = serializeTemplateSimple(doc, 3);
      const lines = serialized.split("\n");
      expect(lines).toHaveLength(3);
      expect(lines[0]).toBe("HI");
      expect(lines[1]).toBe("");
      expect(lines[2]).toBe("");
    });

    it("empty doc with maxLines=3 produces 3 empty lines", () => {
      const doc = parseTemplateSimple("", 3);
      const serialized = serializeTemplateSimple(doc, 3);
      expect(serialized).toBe("\n\n");
    });
  });

  describe("Round-trip (3-line mode)", () => {
    it("round-trips 3 lines of plain text", () => {
      const original = "ONE\nTWO\nTHREE";
      const doc = parseTemplateSimple(original, 3);
      const serialized = serializeTemplateSimple(doc, 3);
      expect(serialized).toBe(original);
    });

    it("round-trips Note template with variables", () => {
      const original = "{{weather.temp}}\n{{red}}\n";
      const doc = parseTemplateSimple(original, 3);
      const serialized = serializeTemplateSimple(doc, 3);
      expect(serialized).toBe(original);
    });

    it("round-trips Note template with fill_space", () => {
      const original = "A{{fill_space}}B\n\n";
      const doc = parseTemplateSimple(original, 3);
      const serialized = serializeTemplateSimple(doc, 3);
      expect(serialized).toBe(original);
    });
  });
});
