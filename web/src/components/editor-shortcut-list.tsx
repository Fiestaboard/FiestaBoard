/**
 * The page editor's `?` shortcut list (slice 2.7, WEB-17) on FiestaUI's
 * `ShortcutListPopover` (1.4d). Figma 07 `57:27771` draws two ways in: the
 * header's secondary "Shortcuts" button (`57:28576`) and the toolbar row's
 * "? All shortcuts" hint (`57:28704`). Both, and the `?` key, open one list
 * (`57:28953`), which 07 hangs in the template column rather than from
 * either trigger, so each popover anchors there: the Template heading, the
 * top of that column (DD-W30).
 *
 * The rows come from `@/lib/editor-shortcuts`, the registry the editor's key
 * handlers read too. Nothing here binds an editing shortcut; this binds only
 * `?`, and never while a text field, the template or another dialog has the
 * key.
 *
 * Touch: the kit hides both triggers where no fine pointer exists (phones);
 * `?` from a hardware keyboard still opens the list.
 */
import { Button, Kbd, ShortcutListPopover, useKbdPlatform } from "@fiestaboard/ui";
import { Zap } from "lucide-react";
import { type RefObject, useCallback, useEffect, useMemo, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import {
  EDITOR_SHORTCUTS,
  type EditorShortcut,
  editorShortcutGroups,
  hasOpenOverlay,
  isTypingTarget,
  matchesShortcut,
  primaryChord,
} from "@/lib/editor-shortcuts";

export type EditorShortcutListVariant = "header" | "hint";

export interface EditorShortcutListState {
  /** Which trigger's popover is open; `?` opens the header's. */
  openFrom: EditorShortcutListVariant | null;
  setOpenFrom: (next: EditorShortcutListVariant | null) => void;
}

/** Inside a dialog, menu or listbox, `?` belongs to that surface. */
const OTHER_SURFACE = '[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"]';

/** The list's open state, and the `?` key that opens it. Mount once per editor. */
export function useEditorShortcutList(): EditorShortcutListState {
  const [openFrom, setOpenFrom] = useState<EditorShortcutListVariant | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.repeat) return;
      if (!matchesShortcut(event, EDITOR_SHORTCUTS.showShortcuts)) return;
      if (isTypingTarget(event.target)) return;
      if (event.target instanceof Element && event.target.closest(OTHER_SURFACE)) return;
      // A modal (the formula editor) or an open picker panel owns the keyboard
      // even when focus is on a control the closest() check cannot see.
      if (hasOpenOverlay()) return;
      event.preventDefault();
      setOpenFrom((current) => current ?? "header");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return { openFrom, setOpenFrom };
}

export interface EditorShortcutListProps {
  variant: EditorShortcutListVariant;
  state: EditorShortcutListState;
  /**
   * The Template heading: the list hangs from it, in the template column.
   * Omit it while that column is hidden (a pixel board's Canvases surface);
   * the kit then hangs the list from the trigger, or its gutter on touch.
   */
  anchorRef?: RefObject<HTMLElement | null>;
  /** The preview binds BoardViewport's keys (`previewBindsBoardViewportKeys`). */
  boardViewport?: boolean;
}

export function EditorShortcutList({ variant, state, anchorRef, boardViewport = false }: EditorShortcutListProps) {
  const t = useTranslations("editorShortcuts");
  const groups = useMemo(() => editorShortcutGroups((key) => t(key), { boardViewport }), [t, boardViewport]);
  const anchor = useCallback(() => anchorRef?.current ?? null, [anchorRef]);
  const { openFrom, setOpenFrom } = state;

  const trigger =
    variant === "header" ? (
      <Button variant="secondary" size="sm" className="h-8 gap-1.5 px-3 text-xs" aria-keyshortcuts="?">
        <Zap className="h-3.5 w-3.5" aria-hidden />
        {t("button")}
      </Button>
    ) : (
      <Button variant="ghost" size="sm" className="text-xs font-normal text-muted-foreground" aria-keyshortcuts="?">
        <Kbd aria-hidden>?</Kbd>
        {t("hint")}
      </Button>
    );

  return (
    <ShortcutListPopover
      trigger={trigger}
      open={openFrom === variant}
      onOpenChange={(open) => setOpenFrom(open ? variant : null)}
      anchor={anchorRef ? anchor : undefined}
      groups={groups}
      footnote={t("footnote")}
      labels={{ title: t("title"), platformNote: t("platformNote"), or: t("or"), close: t("close") }}
    />
  );
}

/**
 * A registry shortcut's first chord as kit `Kbd` caps, spelled for the
 * reader's machine (⌘ ⏎ on Apple, Ctrl Enter elsewhere). Decorative: put
 * `aria-keyshortcuts={ariaKeyShortcuts(shortcut)}` on the control it labels.
 */
export function ShortcutKeys({ shortcut, className }: { shortcut: EditorShortcut; className?: string }) {
  const platform = useKbdPlatform();
  return <Kbd keys={primaryChord(shortcut)} platform={platform} className={className} aria-hidden />;
}
