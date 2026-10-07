/**
 * A pixel board's canvas layers (`layers` from a batch preview or the board's
 * current message) reach FiestaUI's `DisplayPreview` once the installed
 * release takes them (`PREVIEW_TAKES_LAYERS`, FiestaUI#343). Until then the
 * preview draws the cells alone. `DisplayPreview` is stubbed to record props.
 */
import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DevicePreview } from "@/components/device-preview";
import type { CanvasLayerJson } from "@/lib/api";
import { ledLayerProps, PREVIEW_TAKES_LAYERS } from "@/lib/device-preview";

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

const LAYER: CanvasLayerJson = { x: 0, y: 2, width: 1, height: 1, rgba: "/wAA/w==" };

beforeEach(() => {
  seen.length = 0;
});

describe("ledLayerProps", () => {
  it("hands layers on only when the installed DisplayPreview takes them", () => {
    expect(ledLayerProps([LAYER])).toEqual(PREVIEW_TAKES_LAYERS ? { layers: [LAYER] } : {});
  });

  it("is empty when there are no layers", () => {
    expect(ledLayerProps(undefined)).toEqual({});
    expect(ledLayerProps(null)).toEqual({});
    expect(ledLayerProps([])).toEqual({});
  });
});

describe("DevicePreview with canvas layers", () => {
  it("passes an LED board's layers through the gate to DisplayPreview", () => {
    render(
      <DevicePreview model={FIESTAPANEL_LED_MATRIX} message="HI" layers={[LAYER]}>
        <div />
      </DevicePreview>,
    );
    expect(seen).toHaveLength(1);
    expect(seen[0].layers).toEqual(PREVIEW_TAKES_LAYERS ? [LAYER] : undefined);
  });

  it("draws a split-flap board's own children and never DisplayPreview", () => {
    const { getByTestId } = render(
      <DevicePreview model={FIESTAPANEL_SPLIT_FLAP} message="HI" layers={[LAYER]}>
        <div data-testid="flap" />
      </DevicePreview>,
    );
    expect(getByTestId("flap")).toBeTruthy();
    expect(seen).toHaveLength(0);
  });
});
