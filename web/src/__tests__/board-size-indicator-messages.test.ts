import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useTranslations } from "@/i18n/translations";

// Message-level check of the aria wording through the app's own translation
// hook, independent of the @fiestaboard/ui kit (which clamps the grid before
// this app renders it).
function t() {
  return renderHook(() => useTranslations("boardSizeIndicator")).result.current;
}

describe("boardSizeIndicator aria messages (en)", () => {
  // Cols first since slice 2.4: the indicator reads "45 × 3" (07 `57:27771`).
  it("singular row: 8 columns by 1 row", () => {
    expect(t()("ariaLabelColsRows", { rows: 1, cols: 8 })).toBe("8 columns by 1 row");
    expect(t()("ariaLabelColsRowsWithLayout", { rows: 1, cols: 8, layout: "Panel" })).toBe(
      "8 columns by 1 row, Panel",
    );
  });

  it("singular column: 1 column by 3 rows", () => {
    expect(t()("ariaLabelColsRows", { rows: 3, cols: 1 })).toBe("1 column by 3 rows");
  });

  it("plural rows: 13 columns by 3 rows", () => {
    expect(t()("ariaLabelColsRows", { rows: 3, cols: 13 })).toBe("13 columns by 3 rows");
    expect(t()("ariaLabelColsRowsWithLayout", { rows: 3, cols: 13, layout: "Panel" })).toBe(
      "13 columns by 3 rows, Panel",
    );
  });
});
