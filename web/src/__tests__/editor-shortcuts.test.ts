import { describe, expect, it } from "vitest";

import {
  ariaKeyShortcuts,
  BOARD_VIEWPORT_SHORTCUTS,
  codeMirrorKey,
  EDITOR_SHORTCUTS,
  editorShortcutGroups,
  hasOpenOverlay,
  isTypingTarget,
  matchesShortcut,
  previewBindsBoardViewportKeys,
  primaryChord,
  SPLIT_FLAP_PREVIEW_IS_BOARD_VIEWPORT,
} from "@/lib/editor-shortcuts";

function key(k: string, mods: Partial<Pick<KeyboardEvent, "metaKey" | "ctrlKey" | "shiftKey" | "altKey">> = {}) {
  return new KeyboardEvent("keydown", { key: k, ...mods });
}

describe("matchesShortcut", () => {
  it("matches Mod+Z with either Ctrl or ⌘ as the accelerator", () => {
    expect(matchesShortcut(key("z", { ctrlKey: true }), EDITOR_SHORTCUTS.undo)).toBe(true);
    expect(matchesShortcut(key("z", { metaKey: true }), EDITOR_SHORTCUTS.undo)).toBe(true);
  });

  it("does not match undo without the accelerator or with Shift held", () => {
    expect(matchesShortcut(key("z"), EDITOR_SHORTCUTS.undo)).toBe(false);
    expect(matchesShortcut(key("Z", { ctrlKey: true, shiftKey: true }), EDITOR_SHORTCUTS.undo)).toBe(false);
  });

  it("matches both redo alternatives: Mod+Shift+Z and Mod+Y", () => {
    expect(matchesShortcut(key("Z", { metaKey: true, shiftKey: true }), EDITOR_SHORTCUTS.redo)).toBe(true);
    expect(matchesShortcut(key("y", { ctrlKey: true }), EDITOR_SHORTCUTS.redo)).toBe(true);
    expect(matchesShortcut(key("z", { ctrlKey: true }), EDITOR_SHORTCUTS.redo)).toBe(false);
  });

  it("matches Esc against the Escape key", () => {
    expect(matchesShortcut(key("Escape"), EDITOR_SHORTCUTS.closePicker)).toBe(true);
    expect(matchesShortcut(key("Escape", { ctrlKey: true }), EDITOR_SHORTCUTS.closePicker)).toBe(false);
  });

  it("matches ? whichever Shift state the layout needs, but not with an accelerator or Alt", () => {
    expect(matchesShortcut(key("?", { shiftKey: true }), EDITOR_SHORTCUTS.showShortcuts)).toBe(true);
    expect(matchesShortcut(key("?"), EDITOR_SHORTCUTS.showShortcuts)).toBe(true);
    expect(matchesShortcut(key("?", { metaKey: true }), EDITOR_SHORTCUTS.showShortcuts)).toBe(false);
    expect(matchesShortcut(key("?", { altKey: true }), EDITOR_SHORTCUTS.showShortcuts)).toBe(false);
    expect(matchesShortcut(key("/"), EDITOR_SHORTCUTS.showShortcuts)).toBe(false);
  });
});

describe("codeMirrorKey", () => {
  it("spells the formula editor's apply chord the way CodeMirror's keymap reads it", () => {
    expect(codeMirrorKey(EDITOR_SHORTCUTS.applyFormula)).toBe("Mod-Enter");
  });

  it("joins every key of a multi-key chord and maps Esc to Escape", () => {
    expect(codeMirrorKey({ id: "x", labelKey: "x", keys: ["Mod", "Shift", "Z"] })).toBe("Mod-Shift-z");
    expect(codeMirrorKey(EDITOR_SHORTCUTS.closePicker)).toBe("Escape");
  });
});

describe("isTypingTarget", () => {
  it("is true inside inputs, textareas, selects and contenteditable", () => {
    const input = document.createElement("input");
    const textarea = document.createElement("textarea");
    const select = document.createElement("select");
    const editable = document.createElement("div");
    editable.setAttribute("contenteditable", "true");
    const child = document.createElement("span");
    editable.appendChild(child);
    document.body.append(input, textarea, select, editable);
    for (const el of [input, textarea, select, editable, child]) {
      expect(isTypingTarget(el)).toBe(true);
    }
    document.body.innerHTML = "";
  });

  it("is false for buttons, plain elements, contenteditable=false and null", () => {
    const button = document.createElement("button");
    const off = document.createElement("div");
    off.setAttribute("contenteditable", "false");
    document.body.append(button, off);
    expect(isTypingTarget(button)).toBe(false);
    expect(isTypingTarget(off)).toBe(false);
    expect(isTypingTarget(document.body)).toBe(false);
    expect(isTypingTarget(null)).toBe(false);
    document.body.innerHTML = "";
  });
});

describe("editorShortcutGroups", () => {
  const t = (k: string) => `t:${k}`;

  it("lists the editor's bound shortcuts, in order, with their registry keys", () => {
    const [group] = editorShortcutGroups(t);
    expect(group.items.map((i) => i.id)).toEqual(["undo", "redo", "applyFormula", "closePicker", "exitDrawMode"]);
    expect(group.items[0]).toEqual({ id: "undo", label: "t:undo", keys: EDITOR_SHORTCUTS.undo.keys });
    expect(group.items[1].keys).toBe(EDITOR_SHORTCUTS.redo.keys);
  });

  it("never lists the ? key or the BoardViewport keys while the preview has no BoardViewport", () => {
    const ids = editorShortcutGroups(t).flatMap((g) => g.items.map((i) => i.id));
    expect(ids).not.toContain("showShortcuts");
    for (const s of BOARD_VIEWPORT_SHORTCUTS) expect(ids).not.toContain(s.id);
  });

  it("appends BoardViewport's own keys when the preview renders one", () => {
    const ids = editorShortcutGroups(t, { boardViewport: true }).flatMap((g) => g.items.map((i) => i.id));
    expect(ids.slice(-3)).toEqual(["previewStep", "previewEnds", "previewFit"]);
  });

  it("documents BoardViewport's keys exactly as FiestaUI 1.5a binds them", () => {
    expect(BOARD_VIEWPORT_SHORTCUTS.map((s) => s.keys)).toEqual([[["Left"], ["Right"]], [["Home"], ["End"]], ["F"]]);
  });
});

describe("ariaKeyShortcuts and primaryChord", () => {
  it("spells Mod both ways and lists every alternative", () => {
    expect(ariaKeyShortcuts(EDITOR_SHORTCUTS.undo)).toBe("Control+Z Meta+Z");
    expect(ariaKeyShortcuts(EDITOR_SHORTCUTS.redo)).toBe("Control+Shift+Z Meta+Shift+Z Control+Y Meta+Y");
    expect(ariaKeyShortcuts(EDITOR_SHORTCUTS.applyFormula)).toBe("Control+Enter Meta+Enter");
    expect(ariaKeyShortcuts(EDITOR_SHORTCUTS.closePicker)).toBe("Escape");
    expect(ariaKeyShortcuts(EDITOR_SHORTCUTS.showShortcuts)).toBe("?");
  });

  it("returns the first chord of a shortcut", () => {
    expect(primaryChord(EDITOR_SHORTCUTS.redo)).toEqual(["Mod", "Shift", "Z"]);
    expect(primaryChord(EDITOR_SHORTCUTS.undo)).toEqual(["Mod", "Z"]);
  });
});

describe("hasOpenOverlay", () => {
  it("is true while an aria-modal element or a marked app overlay is in the document", () => {
    expect(hasOpenOverlay()).toBe(false);
    const modal = document.createElement("div");
    modal.setAttribute("aria-modal", "true");
    document.body.append(modal);
    expect(hasOpenOverlay()).toBe(true);
    modal.remove();
    const panel = document.createElement("div");
    panel.setAttribute("data-editor-overlay", "");
    document.body.append(panel);
    expect(hasOpenOverlay()).toBe(true);
    panel.remove();
    expect(hasOpenOverlay()).toBe(false);
  });
});

describe("previewBindsBoardViewportKeys", () => {
  it("is false today: the split-flap preview is not a BoardViewport until slice 2.4", () => {
    expect(SPLIT_FLAP_PREVIEW_IS_BOARD_VIEWPORT).toBe(false);
    expect(previewBindsBoardViewportKeys({ ledPreview: false })).toBe(false);
  });

  it("binds only for a split-flap preview once it is a BoardViewport, never for an LED one", () => {
    expect(previewBindsBoardViewportKeys({ ledPreview: false, splitFlapIsViewport: true })).toBe(true);
    expect(previewBindsBoardViewportKeys({ ledPreview: true, splitFlapIsViewport: true })).toBe(false);
  });
});
