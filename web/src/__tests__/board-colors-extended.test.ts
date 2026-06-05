import { describe, expect, it } from "vitest";

import {
  ALL_COLOR_CODES,
  AVAILABLE_COLORS,
  BOARD_COLORS,
  type BoardColorName,
  COLOR_CODE_MAP,
  COLOR_DISPLAY,
  FIESTABOARD_COLORS,
  getBoardColor,
  getFiestaboardColor,
  isValidBoardColor,
  isValidFiestaboardColor,
} from "@/lib/board-colors";

describe("board-colors extended", () => {
  describe("getBoardColor", () => {
    it("returns color by numeric code", () => {
      expect(getBoardColor("63")).toBe(BOARD_COLORS.red);
      expect(getBoardColor("64")).toBe(BOARD_COLORS.orange);
      expect(getBoardColor("65")).toBe(BOARD_COLORS.yellow);
      expect(getBoardColor("66")).toBe(BOARD_COLORS.green);
      expect(getBoardColor("67")).toBe(BOARD_COLORS.blue);
      expect(getBoardColor("68")).toBe(BOARD_COLORS.violet);
      expect(getBoardColor("69")).toBe(BOARD_COLORS.white);
      expect(getBoardColor("70")).toBe(BOARD_COLORS.black);
      expect(getBoardColor("71")).toBe(BOARD_COLORS.black);
    });

    it("returns color by name", () => {
      expect(getBoardColor("red")).toBe(BOARD_COLORS.red);
      expect(getBoardColor("orange")).toBe(BOARD_COLORS.orange);
      expect(getBoardColor("green")).toBe(BOARD_COLORS.green);
      expect(getBoardColor("blue")).toBe(BOARD_COLORS.blue);
      expect(getBoardColor("violet")).toBe(BOARD_COLORS.violet);
      expect(getBoardColor("white")).toBe(BOARD_COLORS.white);
      expect(getBoardColor("black")).toBe(BOARD_COLORS.black);
    });

    it("returns color by name case-insensitively", () => {
      expect(getBoardColor("Red")).toBe(BOARD_COLORS.red);
      expect(getBoardColor("BLUE")).toBe(BOARD_COLORS.blue);
      expect(getBoardColor("Green")).toBe(BOARD_COLORS.green);
    });

    it("returns purple alias as violet", () => {
      expect(getBoardColor("purple")).toBe(BOARD_COLORS.violet);
    });

    it("returns black for unknown values", () => {
      expect(getBoardColor("unknown")).toBe(BOARD_COLORS.black);
      expect(getBoardColor("999")).toBe(BOARD_COLORS.black);
      expect(getBoardColor("")).toBe(BOARD_COLORS.black);
    });
  });

  describe("getFiestaboardColor (backward compat alias)", () => {
    it("is the same function as getBoardColor", () => {
      expect(getFiestaboardColor).toBe(getBoardColor);
    });

    it("works identically", () => {
      expect(getFiestaboardColor("63")).toBe(BOARD_COLORS.red);
      expect(getFiestaboardColor("red")).toBe(BOARD_COLORS.red);
    });
  });

  describe("isValidBoardColor", () => {
    it("returns true for valid numeric codes", () => {
      expect(isValidBoardColor("63")).toBe(true);
      expect(isValidBoardColor("70")).toBe(true);
      expect(isValidBoardColor("71")).toBe(true);
    });

    it("returns true for valid color names", () => {
      expect(isValidBoardColor("red")).toBe(true);
      expect(isValidBoardColor("blue")).toBe(true);
      expect(isValidBoardColor("purple")).toBe(true);
    });

    it("returns true for case-insensitive names", () => {
      expect(isValidBoardColor("Red")).toBe(true);
      expect(isValidBoardColor("BLUE")).toBe(true);
    });

    it("returns false for invalid values", () => {
      expect(isValidBoardColor("unknown")).toBe(false);
      expect(isValidBoardColor("999")).toBe(false);
      expect(isValidBoardColor("")).toBe(false);
    });
  });

  describe("isValidFiestaboardColor (backward compat alias)", () => {
    it("is the same function as isValidBoardColor", () => {
      expect(isValidFiestaboardColor).toBe(isValidBoardColor);
    });
  });

  describe("constant exports", () => {
    it("FIESTABOARD_COLORS is alias of BOARD_COLORS", () => {
      expect(FIESTABOARD_COLORS).toBe(BOARD_COLORS);
    });

    it("BOARD_COLORS has all 8 colors", () => {
      expect(Object.keys(BOARD_COLORS)).toHaveLength(8);
      expect(BOARD_COLORS.red).toBe("#eb4034");
      expect(BOARD_COLORS.white).toBe("#ffffff");
    });

    it("COLOR_CODE_MAP maps all numeric codes", () => {
      expect(COLOR_CODE_MAP["63"]).toBe(BOARD_COLORS.red);
      expect(COLOR_CODE_MAP["71"]).toBe(BOARD_COLORS.black);
    });

    it("ALL_COLOR_CODES includes both numeric and named codes", () => {
      expect(ALL_COLOR_CODES["63"]).toBe(BOARD_COLORS.red);
      expect(ALL_COLOR_CODES["red"]).toBe(BOARD_COLORS.red);
      expect(ALL_COLOR_CODES["purple"]).toBe(BOARD_COLORS.violet);
    });

    it("AVAILABLE_COLORS lists the 8 color names", () => {
      expect(AVAILABLE_COLORS).toHaveLength(8);
      expect(AVAILABLE_COLORS).toContain("red");
      expect(AVAILABLE_COLORS).toContain("black");
    });

    it("COLOR_DISPLAY has entries for all colors", () => {
      for (const color of AVAILABLE_COLORS) {
        const entry = COLOR_DISPLAY[color as BoardColorName];
        expect(entry).toBeDefined();
        expect(entry.bg).toBeDefined();
        expect(entry.text).toBeDefined();
      }
    });

    it("COLOR_DISPLAY white has border class", () => {
      expect(COLOR_DISPLAY.white.bg).toContain("border");
      expect(COLOR_DISPLAY.white.text).toBe("text-board-black");
    });

    it("COLOR_DISPLAY yellow has black text for contrast", () => {
      expect(COLOR_DISPLAY.yellow.text).toBe("text-board-black");
    });
  });
});
