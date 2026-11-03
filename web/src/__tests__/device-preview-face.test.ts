/**
 * A page previews in the face its board draws it at (pagePreviewTarget): a
 * page at the board's own grid previews as the board is now; a page the board
 * produces at another text size previews in that size's model and layout.
 */

import { type DeviceModel, modelWithLedFont, tryResolveDeviceModel } from "@fiestaboard/ui";
import { describe, expect, it } from "vitest";

import { pagePreviewTarget } from "@/lib/device-preview";

// Core sends the model in the board's face (`device_model_spec`); the
// built-in Pixoo 64 id alone resolves to its default 3x5 face.
const PIXOO_IN_5x7 = modelWithLedFont(tryResolveDeviceModel("divoom_pixoo64").model as DeviceModel, "5x7");

const PIXOO_8x10_BOARD = {
  device_type: "panel",
  grid_rows: 8,
  grid_cols: 10,
  device_model: "divoom_pixoo64",
  device_model_spec: PIXOO_IN_5x7,
  producible_grids: { "5x7": [8, 10] as [number, number], "3x5": [10, 16] as [number, number] },
  led_layout: { tile_gap: "gap" as const, block_padding: 0 as const, font: "5x7" as const },
};

describe("pagePreviewTarget", () => {
  it("draws a 10x16 page on an 8x10 Pixoo with the 3x5 model", () => {
    const { model, ledLayout } = pagePreviewTarget(PIXOO_8x10_BOARD, {
      device_type: "panel",
      grid_rows: 10,
      grid_cols: 16,
    });
    expect([model?.font, ledLayout?.font]).toEqual(["3x5", "3x5"]);
  });

  it("leaves the board's own model for a page at its grid", () => {
    const { model, ledLayout } = pagePreviewTarget(PIXOO_8x10_BOARD, {
      device_type: "panel",
      grid_rows: 8,
      grid_cols: 10,
    });
    expect([model?.font, ledLayout?.font]).toEqual(["5x7", "5x7"]);
  });
});
