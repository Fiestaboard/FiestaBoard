import type { DeviceModel } from "@fiestaboard/ui";

/**
 * FiestaPanel's two device models, exactly as `GET /panel/{id}` and
 * `GET /settings/board` send them (`device_model_spec`): FiestaUI's
 * plugin-models.json fixture, vendored in src/fiestaui/plugin-models.json.
 */
export const FIESTAPANEL_SPLIT_FLAP = {
  id: "fiestapanel_split_flap",
  label: "FiestaPanel (split-flap)",
  technology: "split_flap",
  family: "fiestapanel",
  geometry: { kind: "panel", rows: 12, cols: 29 },
  color: { kind: "tiles" },
  charset: "vestaboard_v2",
  animation: { delivery: "none", maxFps: 0 },
  appearance: { boardColors: ["black", "white"], options: { board_color: ["black", "white"] } },
} as unknown as DeviceModel;

export const FIESTAPANEL_LED_MATRIX = {
  id: "fiestapanel_led_matrix",
  label: "FiestaPanel (LED matrix)",
  technology: "led_matrix",
  family: "fiestapanel",
  geometry: { kind: "pixels", width: 192, height: 96 },
  color: { kind: "rgb", bitDepth: 24 },
  charset: "led_5x7",
  animation: { delivery: "stream", maxFps: 60 },
  font: "5x7",
  appearance: { pixelShape: "square", dotRatio: 0.82, offColor: "#1a1a1a", substrateColor: "#000000" },
} as unknown as DeviceModel;
