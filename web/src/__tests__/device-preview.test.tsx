/**
 * Previews follow the board's device model (`device_model` /
 * `device_model_spec` from the API): an LED board is drawn by FiestaUI's
 * `DisplayPreview` as its LED matrix; a split-flap board — or one whose model
 * the app cannot resolve — is the surface's existing split-flap board,
 * untouched.
 */
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DevicePreview } from "@/components/device-preview";
import { charsetTokenText } from "@/lib/charset-issues";
import { boardForShape, isLedModel, ledLetterCase, modelInNewBoardFace, resolveBoardModel } from "@/lib/device-preview";

import { FIESTAPANEL_LED_MATRIX, FIESTAPANEL_SPLIT_FLAP } from "./mocks/fiestapanel-models";

describe("resolveBoardModel", () => {
  it("resolves a built-in model by id", () => {
    expect(resolveBoardModel({ device_model: "divoom_pixoo64" })?.technology).toBe("led_matrix");
  });

  it("prefers the model document the API sends for a model FiestaUI does not build in", () => {
    expect(
      resolveBoardModel({ device_model: "fiestapanel_led_matrix", device_model_spec: FIESTAPANEL_LED_MATRIX })?.id,
    ).toBe("fiestapanel_led_matrix");
  });

  it("draws a Pixoo switched to the large face as the 5x7 model core sends", () => {
    // Core sends the model a board draws as when it differs from FiestaUI's
    // built-in: here the Pixoo in its 5x7 face (text size Large), carrying
    // the face choice (`layoutOptions.font`, FiestaUI #342) the built-in
    // declares from FiestaUI 8.1.0 on.
    const builtin = resolveBoardModel({ device_model: "divoom_pixoo64" })!;
    const spec = {
      ...builtin,
      font: "5x7",
      charset: "led_5x7",
      layoutOptions: {
        tileGap: { allowed: ["gap", "fill"], default: "gap" },
        blockPadding: { allowed: [0, 1], default: 0 },
        font: { allowed: ["5x7", "3x5"], default: "5x7" },
      },
    };
    const model = resolveBoardModel({ device_model: "divoom_pixoo64", device_model_spec: spec as never });
    expect(model?.font).toBe("5x7");
    expect(model?.charset).toBe("led_5x7");
  });

  it("is null for an id it cannot resolve, never a guess", () => {
    expect(resolveBoardModel({ device_model: "acme_unknown" })).toBeNull();
    expect(resolveBoardModel({ device_model: null })).toBeNull();
    expect(resolveBoardModel(null)).toBeNull();
  });
});

describe("modelInNewBoardFace", () => {
  it("draws the face a new board on the model is created in", () => {
    const pixoo = resolveBoardModel({ device_model: "divoom_pixoo64" })!;
    const large = modelInNewBoardFace(pixoo, { new_board_font: "5x7", new_board_charset: "led_5x7" });
    expect(large?.font).toBe("5x7");
    expect(large?.charset).toBe("led_5x7");
  });

  it("is the model itself when the output names no face", () => {
    const pixoo = resolveBoardModel({ device_model: "divoom_pixoo64" })!;
    expect(modelInNewBoardFace(pixoo, { new_board_font: null, new_board_charset: null })).toBe(pixoo);
    expect(modelInNewBoardFace(pixoo, undefined)).toBe(pixoo);
    expect(modelInNewBoardFace(null, { new_board_font: "5x7", new_board_charset: "led_5x7" })).toBeNull();
  });
});

describe("ledLetterCase", () => {
  it("keeps lowercase on a face that carries it, and uppercases one that does not", () => {
    const pixoo = resolveBoardModel({ device_model: "divoom_pixoo64" });
    expect(isLedModel(pixoo)).toBe(true);
    expect(["mixed", "upper"]).toContain(ledLetterCase(pixoo!));
    expect(ledLetterCase(FIESTAPANEL_LED_MATRIX)).toBe("mixed");
  });
});

describe("boardForShape", () => {
  const flagship = { id: "a", device_type: "flagship" as const };
  const flagship2 = { id: "b", device_type: "flagship" as const };
  const note = { id: "n", device_type: "note" as const };

  it("prefers the first preferred board the page fits", () => {
    expect(boardForShape([flagship, flagship2, note], [null, "b"], { device_type: "flagship" })?.id).toBe("b");
  });

  it("skips a preferred board the page does not fit", () => {
    expect(boardForShape([flagship, note], ["n"], { device_type: "flagship" })?.id).toBe("a");
  });

  it("is null when the page fits no board", () => {
    expect(boardForShape([flagship], [], { device_type: "note" })).toBeNull();
  });
});

describe("charsetTokenText", () => {
  it("writes a token the way the editor writes it", () => {
    expect(charsetTokenText({ type: "char", value: "a" })).toBe("a");
    expect(charsetTokenText({ type: "char", value: " " })).toBe("␣");
    expect(charsetTokenText({ type: "color", code: "63" })).toBe("{63}");
    expect(charsetTokenText({ type: "char", value: "x", icon: "heart" })).toBe("{heart}");
  });
});

describe("DevicePreview", () => {
  it("draws an LED model as its LED matrix", () => {
    const { container } = render(
      <DevicePreview model={FIESTAPANEL_LED_MATRIX} message="HELLO">
        <div data-testid="split-flap" />
      </DevicePreview>,
    );
    expect(container.querySelector('[data-slot="display-preview"]')).toHaveAttribute("data-technology", "led_matrix");
    expect(screen.queryByTestId("split-flap")).not.toBeInTheDocument();
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("HELLO");
  });

  it("leaves a split-flap board exactly as the surface draws it", () => {
    const { container } = render(
      <DevicePreview model={FIESTAPANEL_SPLIT_FLAP} message="HELLO">
        <div data-testid="split-flap" />
      </DevicePreview>,
    );
    expect(screen.getByTestId("split-flap")).toBeInTheDocument();
    expect(container.querySelector('[data-slot="display-preview"]')).not.toBeInTheDocument();
  });

  it("leaves the split-flap board when the model is unknown", () => {
    render(
      <DevicePreview model={null} message="HELLO">
        <div data-testid="split-flap" />
      </DevicePreview>,
    );
    expect(screen.getByTestId("split-flap")).toBeInTheDocument();
  });
});
