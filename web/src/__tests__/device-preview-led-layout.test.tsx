/**
 * An LED board's layout choices (`led_layout` from the API: tile gaps filled,
 * block padding) reach FiestaUI's `DisplayPreview` as `tileGap` /
 * `blockPadding`, so the preview draws the bytes the device is sent (plan D23).
 * `DisplayPreview` is stubbed to record its props: the drawing itself is
 * FiestaUI's, golden-tested there.
 */
import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DevicePreview } from "@/components/device-preview";
import { ledLayoutProps, PREVIEW_TAKES_FONT } from "@/lib/device-preview";

import { FIESTAPANEL_LED_MATRIX, FIESTAPANEL_SPLIT_FLAP } from "./mocks/fiestapanel-models";

const seen: Array<Record<string, unknown>> = [];

vi.mock("@fiestaboard/ui", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@fiestaboard/ui")>();
  return {
    ...actual,
    DisplayPreview: (props: Record<string, unknown>) => {
      seen.push(props);
      return null;
    },
  };
});

beforeEach(() => {
  seen.length = 0;
});

describe("ledLayoutProps", () => {
  it("maps the API's snake_case choice to DisplayPreview's props", () => {
    expect(ledLayoutProps({ tile_gap: "fill", block_padding: 1 })).toEqual({ tileGap: "fill", blockPadding: 1 });
    expect(ledLayoutProps({ tile_gap: "gap", block_padding: 0 })).toEqual({ tileGap: "gap", blockPadding: 0 });
  });

  it("hands the board's face to a DisplayPreview that takes one", () => {
    // FiestaUI 8.0.0's DisplayPreview has no `font` prop: until the bump to
    // the release with FiestaUI #342, the face reaches the preview through
    // the model document core sends (`device_model_spec`) instead.
    const props = ledLayoutProps({ tile_gap: "gap", block_padding: 0, font: "5x7" });
    expect(props).toEqual(
      PREVIEW_TAKES_FONT ? { tileGap: "gap", blockPadding: 0, font: "5x7" } : { tileGap: "gap", blockPadding: 0 },
    );
  });

  it("is empty for a board that sends none, so the model's defaults draw", () => {
    expect(ledLayoutProps(undefined)).toEqual({});
    expect(ledLayoutProps(null)).toEqual({});
  });
});

describe("DevicePreview with an LED board's layout", () => {
  it("hands the board's tile gap and block padding to DisplayPreview", () => {
    render(
      <DevicePreview model={FIESTAPANEL_LED_MATRIX} message="HI" ledLayout={{ tile_gap: "fill", block_padding: 1 }}>
        <div />
      </DevicePreview>,
    );
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ tileGap: "fill", blockPadding: 1, message: "HI" });
  });

  it("passes neither when the board sends no layout", () => {
    render(
      <DevicePreview model={FIESTAPANEL_LED_MATRIX} message="HI">
        <div />
      </DevicePreview>,
    );
    expect(seen[0]).not.toHaveProperty("tileGap");
    expect(seen[0]).not.toHaveProperty("blockPadding");
  });

  it("draws a split-flap board as its own board, layout or not", () => {
    render(
      <DevicePreview model={FIESTAPANEL_SPLIT_FLAP} message="HI" ledLayout={{ tile_gap: "fill", block_padding: 1 }}>
        <div />
      </DevicePreview>,
    );
    expect(seen).toHaveLength(0);
  });
});
