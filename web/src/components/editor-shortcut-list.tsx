/**
 * The page editor's `?` shortcut list (slice 2.7, WEB-17) on FiestaUI's
 * `ShortcutListPopover` (1.4d). The toolbar row's "? All shortcuts" hint
 * (07 `57:28704`) is the one way in (DD-W161, editor UX D5: help sits beside
 * the tools it explains); `?` and ⌘/ open the same list (`57:28953`), which
 * 07 hangs in the template column rather than from the trigger, so the
 * popover anchors there: the Template heading, the top of that column
 * (DD-W30). The `header` variant remains only until the header stops
 * rendering it; while both are mounted the keys open the hint's popover.
 *
 * The rows come from `@/lib/editor-shortcuts`, the registry the editor's key
 * handlers read too. Nothing here binds an editing shortcut; this binds only
 * `?` (never while a text field, the template or another dialog has the
 * key) and ⌘/ (also from the template, as Docs does; never inside another
 * dialog).
 *
 * Touch: the kit hides both triggers where no fine pointer exists (phones);
 * `?` from a hardware keyboard still opens the list.
 */
import { Button, Kbd, ShortcutListPopover, useKbdPlatform } from "@fiestaboard/ui";
import { Zap } from "lucide-react";
import { type RefObject, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import {
  ariaKeyShortcuts,
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
  /** Which trigger's popover is open; the keys open the hint's when it is mounted. */
  openFrom: EditorShortcutListVariant | null;
  setOpenFrom: (next: EditorShortcutListVariant | null) => void;
  /** A mounted trigger registers itself, so the keys open a popover that exists. Returns the cleanup. */
  register: (variant: EditorShortcutListVariant) => () => void;
}

/** Inside a dialog, menu or listbox, `?` belongs to that surface. */
const OTHER_SURFACE = '[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"]';

/** The list's open state, and the `?` / ⌘/ keys that open it. Mount once per editor. */
export function useEditorShortcutList(): EditorShortcutListState {
  const [openFrom, setOpenFrom] = useState<EditorShortcutListVariant | null>(null);
  const mounted = useRef(new Map<EditorShortcutListVariant, number>());

  const register = useCallback((variant: EditorShortcutListVariant) => {
    const counts = mounted.current;
    counts.set(variant, (counts.get(variant) ?? 0) + 1);
    return () => counts.set(variant, (counts.get(variant) ?? 1) - 1);
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.repeat) return;
      if (!matchesShortcut(event, EDITOR_SHORTCUTS.showShortcuts)) return;
      // `?` is a character while typing; ⌘/ is not, so it works from the template too.
      const chord = event.metaKey || event.ctrlKey;
      if (!chord && isTypingTarget(event.target)) return;
      if (event.target instanceof Element && event.target.closest(OTHER_SURFACE)) return;
      // A modal (the formula editor) or an open picker panel owns the keyboard
      // even when focus is on a control the closest() check cannot see.
      if (hasOpenOverlay()) return;
      event.preventDefault();
      const target: EditorShortcutListVariant = (mounted.current.get("hint") ?? 0) > 0 ? "hint" : "header";
      setOpenFrom((current) => current ?? target);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return { openFrom, setOpenFrom, register };
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
  /** The header trigger in a tight desktop header: icon only, named "Shortcuts" (BB-E-4). */
  compact?: boolean;
  /** The preview binds BoardViewport's keys (`previewBindsBoardViewportKeys`). */
  boardViewport?: boolean;
}

export function EditorShortcutList({
  variant,
  state,
  anchorRef,
  boardViewport = false,
  compact = false,
}: EditorShortcutListProps) {
  const t = useTranslations("editorShortcuts");
  const groups = useMemo(() => editorShortcutGroups((key) => t(key), { boardViewport }), [t, boardViewport]);
  const anchor = useCallback(() => anchorRef?.current ?? null, [anchorRef]);
  const { openFrom, setOpenFrom, register } = state;
  const compactHeader = variant === "header" && compact;
  useEffect(() => register(variant), [register, variant]);

  const trigger =
    variant === "header" ? (
      <Button
        variant="ghost"
        size="lg"
        className="gap-1.5 px-4 text-sm"
        aria-keyshortcuts={ariaKeyShortcuts(EDITOR_SHORTCUTS.showShortcuts)}
        aria-label={compactHeader ? t("button") : undefined}
      >
        <Zap className="h-3.5 w-3.5" aria-hidden />
        {/* 1024–1279: icon only beside the page name (BB-E-4). */}
        {!compactHeader && t("button")}
      </Button>
    ) : (
      <Button
        variant="ghost"
        size="sm"
        className="text-xs font-normal text-muted-foreground"
        aria-keyshortcuts={ariaKeyShortcuts(EDITOR_SHORTCUTS.showShortcuts)}
      >
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
