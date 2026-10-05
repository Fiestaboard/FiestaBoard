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
  type LedLetterCase,
  tryResolveCharacterSet,
  tryResolveDeviceModel,
} from "@fiestaboard/ui";

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
