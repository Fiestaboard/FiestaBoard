/**
 * The page editor's keyboard shortcuts — ONE registry that both the key
 * handlers and the `?` list (FiestaUI `ShortcutListPopover`, slice 2.7 /
 * WEB-17) read, so the list can never describe a key the editor does not
 * bind, and a binding cannot change without the list changing with it.
 *
 * Every handler that implements one of these calls `matchesShortcut` (DOM
 * handlers) or `codeMirrorKey` (the formula editor's CodeMirror keymap) with
 * its entry here, instead of spelling its own keys.
 *
 * Key names follow FiestaUI `Kbd`: "Mod" is ⌘ on Apple and Ctrl elsewhere.
 * Like the handlers it replaced, a "Mod" chord accepts either Ctrl or ⌘ on
 * every platform.
 *
 * Only shortcuts that exist are listed (audit in
 * docs/internal/plans/2026-11-13-universal-web-2.7.md). 07 `57:28953` also
 * draws `/` (Insert) and ⌘⇧L/E/R (align); they join this registry with
 * their bindings, not before. `saveAndShow` (⌘⇧S) is registered for the
 * handler that will bind it (editor UX FP-1) and joins `LISTED` in the same
 * change as its binding. `previewActualSize` (1) is bound by the preview's
 * View menu (FP-3, `PreviewHeaderControls`) and listed with the preview keys.
 */
import type { ShortcutChord, ShortcutGroup } from "@fiestaboard/ui";

export interface EditorShortcut {
  id: string;
  /** Message key under `editorShortcuts`. */
  labelKey: string;
  /** One chord, or several alternatives (`[["Mod","Shift","Z"],["Mod","Y"]]`). */
  keys: ShortcutChord | readonly ShortcutChord[];
}

export const EDITOR_SHORTCUTS = {
  undo: { id: "undo", labelKey: "undo", keys: ["Mod", "Z"] },
  redo: {
    id: "redo",
    labelKey: "redo",
    keys: [
      ["Mod", "Shift", "Z"],
      ["Mod", "Y"],
    ],
  },
  applyFormula: { id: "applyFormula", labelKey: "applyFormula", keys: ["Mod", "Enter"] },
  closePicker: { id: "closePicker", labelKey: "closePicker", keys: ["Esc"] },
  exitDrawMode: { id: "exitDrawMode", labelKey: "exitDrawMode", keys: ["Esc"] },
  /** Inserts a formula at the caret (the template editor; Docs' ⌘E-style chord). */
  insertFormula: { id: "insertFormula", labelKey: "insertFormula", keys: ["Mod", "E"] },
  /** Save / Save draft (PageBuilder's key handler). */
  save: { id: "save", labelKey: "save", keys: ["Mod", "S"] },
  /** Show now / Save & update board: the header primary (PageBuilder's key handler, FP-1). */
  saveAndShow: { id: "saveAndShow", labelKey: "saveAndShow", keys: ["Mod", "Shift", "S"] },
  /** Toggles Inspect on the desktop preview (`use-formula-ide`). */
  inspect: { id: "inspect", labelKey: "inspect", keys: ["I"] },
  /** Actual size: the preview View menu's key (`PreviewHeaderControls`, FP-3), outside text. */
  previewActualSize: { id: "previewActualSize", labelKey: "previewActualSize", keys: ["1"] },
  /**
   * Opens the list itself; not a row of the list. `?` outside text, and
   * ⌘/ anywhere, the Docs convention (UX-9-1).
   */
  showShortcuts: { id: "showShortcuts", labelKey: "showShortcuts", keys: [["?"], ["Mod", "/"]] },
} as const satisfies Record<string, EditorShortcut>;

/** The list's groups, as Docs groups its list (UX-9-1). */
type ListGroupId = "editing" | "document" | "preview";

/** The rows of the list, in 07's order where 07 draws them. */
const LISTED: readonly { group: ListGroupId; shortcut: EditorShortcut }[] = [
  { group: "editing", shortcut: EDITOR_SHORTCUTS.undo },
  { group: "editing", shortcut: EDITOR_SHORTCUTS.redo },
  { group: "editing", shortcut: EDITOR_SHORTCUTS.insertFormula },
  { group: "editing", shortcut: EDITOR_SHORTCUTS.applyFormula },
  { group: "editing", shortcut: EDITOR_SHORTCUTS.closePicker },
  { group: "editing", shortcut: EDITOR_SHORTCUTS.exitDrawMode },
  { group: "document", shortcut: EDITOR_SHORTCUTS.save },
  { group: "document", shortcut: EDITOR_SHORTCUTS.saveAndShow },
  { group: "preview", shortcut: EDITOR_SHORTCUTS.inspect },
];

/**
 * BoardViewport's own keys (FiestaUI 1.5a, #387): ← → page the preview by
 * one Note, array column or tile column, Home / End jump to the ends, F
 * toggles Fit / Actual size, while the preview is focused. The kit binds
 * them; this app only documents them, and only while the editor preview IS
 * a BoardViewport — see `previewBindsBoardViewportKeys`. Jev 2026-11-13
 * `gate_on_viewport`, p 0.91.
 */
export const BOARD_VIEWPORT_SHORTCUTS: readonly EditorShortcut[] = [
  {
    id: "previewStep",
    labelKey: "previewStep",
    keys: [["Left"], ["Right"]],
  },
  {
    id: "previewEnds",
    labelKey: "previewEnds",
    keys: [["Home"], ["End"]],
  },
  { id: "previewFit", labelKey: "previewFit", keys: ["F"] },
];

/**
 * Whether the editor's split-flap preview renders FiestaUI's BoardViewport.
 * Slice 2.4 converts the app's `ScaledBoardDisplay` wrapper, the editor's
 * split-flap renderer, so the list includes the kit's active preview bindings.
 */
export const SPLIT_FLAP_PREVIEW_IS_BOARD_VIEWPORT = true;

/**
 * Whether the preview binds BoardViewport's keys: only a split-flap preview
 * can (BoardViewport draws flaps only; an LED board previews through
 * `DevicePreview`, which never binds them — 2.4 gap G3).
 */
export function previewBindsBoardViewportKeys({
  ledPreview,
  splitFlapIsViewport = SPLIT_FLAP_PREVIEW_IS_BOARD_VIEWPORT,
}: {
  ledPreview: boolean;
  splitFlapIsViewport?: boolean;
}): boolean {
  return splitFlapIsViewport && !ledPreview;
}

/**
 * Marks an open app overlay that has no ARIA modal semantics of its own (a
 * toolbar picker panel). While one is open, `?` belongs to it.
 */
export const EDITOR_OVERLAY_ATTR = "data-editor-overlay";

/** An open modal (`aria-modal`) or app overlay owns the keyboard. */
export function hasOpenOverlay(doc: Document = document): boolean {
  return Array.from(doc.querySelectorAll(`[aria-modal="true"], [${EDITOR_OVERLAY_ATTR}]`)).some(
    // Closed drawers may stay mounted for their exit animation and retain
    // modal semantics. Their hidden/inert subtree does not own the keyboard.
    (overlay) => !overlay.closest('[aria-hidden="true"], [inert], [hidden]'),
  );
}

function toChords(keys: EditorShortcut["keys"]): readonly ShortcutChord[] {
  return typeof keys[0] === "string" ? [keys as ShortcutChord] : (keys as readonly ShortcutChord[]);
}

const MODIFIERS = new Set(["mod", "shift", "alt"]);
/** `Kbd` names → `KeyboardEvent.key`. */
const KEY_ALIASES: Record<string, string> = {
  esc: "escape",
  left: "arrowleft",
  right: "arrowright",
  up: "arrowup",
  down: "arrowdown",
};

function eventKeyName(name: string): string {
  const lower = name.toLowerCase();
  return KEY_ALIASES[lower] ?? lower;
}

function matchesChord(event: KeyboardEvent, chord: ShortcutChord): boolean {
  const names = chord.map((k) => k.toLowerCase());
  const main = names.find((k) => !MODIFIERS.has(k));
  if (main === undefined || event.key.toLowerCase() !== eventKeyName(main)) return false;
  const wantsMod = names.includes("mod");
  if ((event.metaKey || event.ctrlKey) !== wantsMod) return false;
  if (event.altKey !== names.includes("alt")) return false;
  // A symbol such as "?" already implies whatever Shift its layout needs.
  const isSymbol = main.length === 1 && !/[a-z0-9]/.test(main);
  return isSymbol || event.shiftKey === names.includes("shift");
}

const ARIA_KEY_NAMES: Record<string, string> = { esc: "Escape", left: "ArrowLeft", right: "ArrowRight" };

/**
 * The shortcut as an `aria-keyshortcuts` value: every alternative, with
 * "Mod" spelled both ways ("Control+Z Meta+Z"), as the handlers accept both.
 */
export function ariaKeyShortcuts(shortcut: EditorShortcut): string {
  const spell = (chord: ShortcutChord, mod: string) =>
    chord
      .map((k) => {
        const lower = k.toLowerCase();
        if (lower === "mod") return mod;
        if (lower === "shift") return "Shift";
        if (lower === "alt") return "Alt";
        return ARIA_KEY_NAMES[lower] ?? (k.length === 1 ? k.toUpperCase() : k);
      })
      .join("+");
  return toChords(shortcut.keys)
    .flatMap((chord) =>
      chord.some((k) => k.toLowerCase() === "mod")
        ? [spell(chord, "Control"), spell(chord, "Meta")]
        : [spell(chord, "")],
    )
    .join(" ");
}

const CHORD_TEXT: Record<string, { apple: string; generic: string }> = {
  mod: { apple: "⌘", generic: "Ctrl" },
  shift: { apple: "⇧", generic: "Shift" },
  alt: { apple: "⌥", generic: "Alt" },
  enter: { apple: "⏎", generic: "Enter" },
  esc: { apple: "Esc", generic: "Esc" },
};

/**
 * A chord as tooltip text, in `Kbd`'s spelling: "⌘⇧Z" on Apple, "Ctrl+Shift+Z"
 * elsewhere ("Undo (⌘Z)", the Word/Docs grammar of UX-2-3).
 */
export function chordText(chord: ShortcutChord, platform: "apple" | "generic"): string {
  const keys = chord.map((k) => CHORD_TEXT[k.toLowerCase()]?.[platform] ?? (k.length === 1 ? k.toUpperCase() : k));
  return platform === "apple" ? keys.join("") : keys.join("+");
}

/** The first chord, for a single inline hint (a tooltip or a button). */
export function primaryChord(shortcut: EditorShortcut): ShortcutChord {
  return toChords(shortcut.keys)[0];
}

/** Whether a keydown is this shortcut (any of its alternatives). */
export function matchesShortcut(event: KeyboardEvent, shortcut: EditorShortcut): boolean {
  return toChords(shortcut.keys).some((chord) => matchesChord(event, chord));
}

/** The first chord, spelled for a CodeMirror `keymap` (`"Mod-Enter"`). */
export function codeMirrorKey(shortcut: EditorShortcut): string {
  const [chord] = toChords(shortcut.keys);
  return chord
    .map((k) => {
      const lower = k.toLowerCase();
      if (MODIFIERS.has(lower)) return k[0].toUpperCase() + k.slice(1).toLowerCase();
      if (lower === "esc") return "Escape";
      return k.length === 1 ? lower : k;
    })
    .join("-");
}

/**
 * Where a single-key shortcut must stay a typed character: inputs,
 * textareas, selects and contenteditable (the template and formula editors).
 */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof Element)) return false;
  if (target.closest("input, textarea, select")) return true;
  const editable = target.closest("[contenteditable]");
  return editable !== null && editable.getAttribute("contenteditable") !== "false";
}

const GROUP_ORDER: readonly ListGroupId[] = ["editing", "document", "preview"];
const GROUP_TITLE_KEYS: Record<ListGroupId, string> = {
  editing: "groupEditing",
  document: "groupDocument",
  preview: "groupPreview",
};

/**
 * The list's data: the registry's rows, labelled through `t`, in Editing ·
 * Document · Preview groups (empty groups are left out).
 */
export function editorShortcutGroups(
  t: (key: string) => string,
  { boardViewport = false }: { boardViewport?: boolean } = {},
): ShortcutGroup[] {
  // The View menu binds F (Fit / Actual size, as BoardViewport does while
  // focused) and 1 (Actual size) outside text wherever the preview zooms (FP-3).
  const previewKeys = [...BOARD_VIEWPORT_SHORTCUTS, EDITOR_SHORTCUTS.previewActualSize];
  const rows = boardViewport
    ? [...LISTED, ...previewKeys.map((shortcut) => ({ group: "preview" as const, shortcut }))]
    : LISTED;
  return GROUP_ORDER.map((group) => ({
    id: group,
    title: t(GROUP_TITLE_KEYS[group]),
    items: rows
      .filter((row) => row.group === group)
      .map(({ shortcut: s }) => ({ id: s.id, label: t(s.labelKey), keys: s.keys })),
  })).filter((group) => group.items.length > 0);
}
