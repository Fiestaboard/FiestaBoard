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
  it("singular row: 1 row by 8 columns", () => {
    expect(t()("ariaLabel", { rows: 1, cols: 8 })).toBe("1 row by 8 columns");
    expect(t()("ariaLabelWithLayout", { rows: 1, cols: 8, layout: "Panel" })).toBe(
      "1 row by 8 columns, Panel",
    );
  });

  it("plural rows: 3 rows by 13 columns", () => {
    expect(t()("ariaLabel", { rows: 3, cols: 13 })).toBe("3 rows by 13 columns");
    expect(t()("ariaLabelWithLayout", { rows: 3, cols: 13, layout: "Panel" })).toBe(
      "3 rows by 13 columns, Panel",
    );
  });
});
