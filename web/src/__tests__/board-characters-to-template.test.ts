import { describe, expect, it } from "vitest";

import { boardCharactersToTemplate } from "@/lib/board-characters-to-template";

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
    expect(boardCharactersToTemplate([[1, 0, 0], [0, 0, 0], [0, 2, 0]])).toEqual(["A", "", " B"]);
  });

  it("renders undefined and out-of-range codes as blanks", () => {
    expect(boardCharactersToTemplate([[43, 1, 99, 2, -1, 3]])).toEqual([" A B C"]);
  });
});
