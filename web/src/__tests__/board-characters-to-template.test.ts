import { describe, expect, it } from "vitest";

import { boardCharactersToTemplate, buildBoardPageCreate } from "@/lib/board-characters-to-template";

describe("boardCharactersToTemplate", () => {
  it("maps letter, digit and punctuation codes to their characters", () => {
    // H=8 I=9 space=0 1=27 0=36 !=37 °=62
    expect(boardCharactersToTemplate([[8, 9, 0, 27, 36, 37, 62]])).toEqual(["HI 10!°"]);
  });

  it("maps color tile codes to {{color}} markers", () => {
    expect(boardCharactersToTemplate([[63, 64, 65, 66, 67, 68, 69, 70, 71]])).toEqual([
      "{{red}}{{orange}}{{yellow}}{{green}}{{blue}}{{violet}}{{white}}{{black}}{{black}}",
    ]);
  });

  it("produces one line per row and trims trailing blanks", () => {
    expect(
      boardCharactersToTemplate([
        [1, 0, 0],
        [0, 0, 0],
        [0, 2, 0],
      ]),
    ).toEqual(["A", "", " B"]);
  });

  it("renders undefined and out-of-range codes as blanks", () => {
    expect(boardCharactersToTemplate([[43, 1, 99, 2, -1, 3]])).toEqual([" A B C"]);
  });
});

describe("buildBoardPageCreate", () => {
  // Row 0 reads "HI" followed by a red tile; the second row is blank.
  const hiRed = [
    [8, 9, 63, 0],
    [0, 0, 0, 0],
  ];

  it("builds a template page for a flagship with no geometry extras", () => {
    const body = buildBoardPageCreate(hiRed, { deviceType: "flagship", notesWide: 1, notesTall: 1 }, "Saved");

    expect(body).toEqual({
      name: "Saved",
      type: "template",
      device_type: "flagship",
      template: ["HI{{red}}", ""],
    });
  });

  it("carries notes_wide/notes_tall for a note array", () => {
    const body = buildBoardPageCreate(hiRed, { deviceType: "note_array", notesWide: 2, notesTall: 3 }, "Saved");

    expect(body).toMatchObject({ device_type: "note_array", notes_wide: 2, notes_tall: 3 });
    expect(body).not.toHaveProperty("grid_rows");
    expect(body).not.toHaveProperty("grid_cols");
  });

  it("carries grid_rows/grid_cols for a panel", () => {
    const body = buildBoardPageCreate(
      hiRed,
      { deviceType: "panel", notesWide: 1, notesTall: 1, gridRows: 12, gridCols: 29 },
      "Saved",
    );

    expect(body).toMatchObject({ device_type: "panel", grid_rows: 12, grid_cols: 29 });
    expect(body).not.toHaveProperty("notes_wide");
  });

  it("falls back to the grid's own dimensions for a panel without stored geometry", () => {
    const body = buildBoardPageCreate(hiRed, { deviceType: "panel", notesWide: 1, notesTall: 1 }, "Saved");

    expect(body).toMatchObject({ grid_rows: 2, grid_cols: 4 });
  });

  it("takes its template rows from boardCharactersToTemplate", () => {
    const body = buildBoardPageCreate(hiRed, { deviceType: "note", notesWide: 1, notesTall: 1 }, "Saved");

    expect(body.template).toEqual(boardCharactersToTemplate(hiRed));
    expect(body.template?.[0]).toBe("HI{{red}}");
  });
});
