/**
 * Which device a preview draws, from what the API says about a board.
 *
 * Every board response carries the FiestaUI device model it resolves to
 * (`device_model`, an id) and — when FiestaUI does not build that model in
 * (a FiestaPanel's, an output plugin's own) — the model's document
 * (`device_model_spec`). `DisplayPreview` resolves a built-in by id and
 * anything else only from the document, and throws for an id it does not
 * know; a preview must never crash a page over a hint, so an unresolvable
 * model is `null` here and the caller draws today's split-flap board.
 */

import {
  type CharacterSet,
  characterSetForModel,
  type DeviceModel,
  type DisplayPreview,
  type LedLetterCase,
  tryResolveCharacterSet,
  tryResolveDeviceModel,
} from "@fiestaboard/ui";
import type { ComponentProps } from "react";

import type { BoardLedLayout, LedFontId, OutputDeviceModel } from "@/lib/api";
import { pagesCompatibleWithBoard, type SizedEntity } from "@/lib/board-dimensions";

/**
 * The board a page of `shape` is previewed (and charset-checked) as: the
 * first of `preferredIds` whose size the page fits, else the first board it
 * fits; `null` when it fits none. A page belongs to a size, not a board, so
 * a board of another size never lends it a model or a character set.
 */
export function boardForShape<B extends SizedEntity & { id: string }>(
  boards: readonly B[] | null | undefined,
  preferredIds: ReadonlyArray<string | null | undefined>,
  shape: SizedEntity,
): B | null {
  if (!boards?.length) return null;
  const fits = boards.filter((b) => pagesCompatibleWithBoard(shape, b));
  for (const id of preferredIds) {
    const preferred = id ? fits.find((b) => b.id === id) : undefined;
    if (preferred) return preferred;
  }
  return fits[0] ?? null;
}

/** The model fields a board (or panel) response carries. */
export interface BoardModelFields {
  device_model?: string | null;
  device_model_spec?: DeviceModel | null;
}

/** The board's device model: its document when sent, else its built-in id; `null` when neither resolves. */
export function resolveBoardModel(board: BoardModelFields | null | undefined): DeviceModel | null {
  if (!board) return null;
  if (board.device_model_spec) {
    const resolved = tryResolveDeviceModel(board.device_model_spec);
    if (resolved.model) return resolved.model;
  }
  if (typeof board.device_model === "string" && board.device_model) {
    const resolved = tryResolveDeviceModel(board.device_model);
    if (resolved.model) return resolved.model;
  }
  return null;
}

/** True when the model is an LED matrix — the boards a split-flap renderer cannot draw. */
export function isLedModel(model: DeviceModel | null | undefined): model is DeviceModel {
  return model?.technology === "led_matrix";
}

/** `DisplayPreview`'s LED layout props (FiestaUI `tileGap` / `blockPadding` / `font`). */
export interface LedLayoutProps {
  tileGap?: "gap" | "fill";
  blockPadding?: 0 | 1;
  font?: LedFontId;
}

/**
 * Whether this FiestaUI release's `DisplayPreview` takes a `font` prop
 * (FiestaUI #342, the release after 8.0.0). Until it does, a board's face
 * reaches the preview through the model document core sends instead
 * (`device_model_spec`: the model in the board's face), so nothing is lost.
 * The `satisfies` fails to compile once the bumped release takes `font`:
 * flip it to `true` then.
 */
export const PREVIEW_TAKES_FONT = false satisfies PreviewTakesFont;
type PreviewTakesFont = "font" extends keyof ComponentProps<typeof DisplayPreview> ? true : false;

/**
 * An LED board's layout choices (`led_layout` from the API) as
 * `DisplayPreview` props, so the preview draws the bytes the device is sent:
 * the gutter between same-colour tiles filled (`tileGap: "fill"`), a block's
 * background grown a pixel (`blockPadding: 1`). Empty for a board that sends
 * none, which draws its model's defaults. A FiestaUI release without the two
 * props ignores them.
 */
export function ledLayoutProps(layout: BoardLedLayout | null | undefined): LedLayoutProps {
  if (!layout) return {};
  const props: LedLayoutProps = { tileGap: layout.tile_gap, blockPadding: layout.block_padding };
  if (PREVIEW_TAKES_FONT && layout.font) props.font = layout.font;
  return props;
}

/**
 * The model a NEW board on `model` draws as: the model in the face the output
 * says a new board is created in (`new_board_font` / `new_board_charset` from
 * `GET /outputs`; a Pixoo 64 is created Large, 5x7). `model` itself when the
 * output names no face, or it is the model's own.
 */
export function modelInNewBoardFace(
  model: DeviceModel | null,
  face: Pick<OutputDeviceModel, "new_board_font" | "new_board_charset"> | null | undefined,
): DeviceModel | null {
  if (!model || !face?.new_board_font || !face.new_board_charset) return model;
  if (face.new_board_font === model.font) return model;
  // The set id is core's (`led_charset_for_font`); FiestaUI validates it.
  const charset = face.new_board_charset as DeviceModel["charset"];
  const resolved = tryResolveDeviceModel({ ...model, font: face.new_board_font, charset });
  return resolved.model ?? model;
}

/**
 * Whether an LED face keeps a message's lowercase. Core does not uppercase
 * for a set that carries lowercase (`mixedCase`), so neither may the preview.
 */
export function ledLetterCase(model: DeviceModel): LedLetterCase {
  try {
    return characterSetForModel(model).mixedCase ? "mixed" : "upper";
  } catch {
    return "upper";
  }
}

/**
 * The character set an LED board's editor writes for: the board's own set
 * when the API names a built-in one (`charset`, which may differ from the
 * model's default — a Pixoo drawn in the 3×5 face), else the set its model
 * declares (an output plugin's own set arrives in the model document).
 * `null` for a split-flap or unknown board: its editor stays the flap editor.
 */
export function ledEditorCharacterSet(
  board: { charset?: string | null } | null | undefined,
  model: DeviceModel | null | undefined,
): CharacterSet | null {
  if (!isLedModel(model)) return null;
  if (board?.charset) {
    const byId = tryResolveCharacterSet(board.charset);
    if (byId.set) return byId.set;
  }
  try {
    return characterSetForModel(model);
  } catch {
    return null;
  }
}
