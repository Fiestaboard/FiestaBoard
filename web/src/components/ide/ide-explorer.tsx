"use client";

import {
  Box,
  Button,
  Card,
  ListRow,
  ListRowGroup,
  Stack,
  Text,
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@fiestaboard/ui";
import { PanelLeft } from "lucide-react";
import { type ReactNode, useCallback, useEffect, useId, useMemo, useRef } from "react";

import { useTranslations } from "@/i18n/translations";
import type { DeviceType } from "@/lib/api";
import { hasOpenOverlay, isTypingTarget } from "@/lib/editor-shortcuts";
import { useExplorerOpen } from "@/lib/ide/explorer-pref";
import type { TemplateReferences } from "@/lib/ide/references";

import type { CreatorIdeState } from "./use-creator-ide";

function GroupLabel({ id, children }: { id: string; children: React.ReactNode }) {
  return (
    <Text as="p" id={id} size="xs" tone="muted" className="font-mono uppercase tracking-wide pt-2">
      {children}
    </Text>
  );
}

/**
 * The Explorer's open state for this board kind (D2) and its one toggle's
 * ref (UX-5-1): the toggle stays in the toolbar row open or closed, so focus
 * stays on it; dismissing the overlay (D8) puts focus back on it.
 */
export function useExplorerToggle(kind: DeviceType) {
  const [open, setOpen] = useExplorerOpen(kind);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const toggle = useCallback(() => setOpen(!open), [open, setOpen]);
  /** Closes it, and by default returns focus to the toggle (the overlay's Esc and click-outside). */
  const dismiss = useCallback(
    (refocus = true) => {
      setOpen(false);
      if (refocus) buttonRef.current?.focus();
    },
    [setOpen],
  );
  return { open, toggle, dismiss, buttonRef };
}

export type ExplorerToggle = ReturnType<typeof useExplorerToggle>;

/**
 * D8 (DD-W157): at 1024–1279 px the open Explorer is a panel over the
 * template, so it dismisses like one (FABLE-2652 §3.6): Esc, or a press
 * outside it and its toggle, closes it. Esc returns focus to the toggle; a
 * press outside leaves focus where the press puts it, except that focus
 * inside the closing panel goes back to the toggle rather than to <body>.
 */
export function useExplorerOverlayDismiss(toggle: ExplorerToggle, panel: HTMLElement | null, overlay: boolean) {
  const { open, dismiss, buttonRef } = toggle;
  useEffect(() => {
    if (!open || !overlay || !panel) return;
    const inside = (target: EventTarget | null) =>
      target instanceof Node && (panel.contains(target) || !!buttonRef.current?.contains(target));
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      // A dialog or picker owns its Esc; so does a text field outside the panel (rename, template).
      if (hasOpenOverlay()) return;
      if (isTypingTarget(event.target) && !inside(event.target)) return;
      dismiss();
    };
    const onPointer = (event: PointerEvent) => {
      if (inside(event.target)) return;
      // A press inside a dialog or menu opened over the editor is not "outside" the panel.
      if (
        event.target instanceof Element &&
        event.target.closest('[role="dialog"], [role="alertdialog"], [role="menu"]')
      )
        return;
      dismiss(panel.contains(document.activeElement));
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer, true);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer, true);
    };
  }, [open, overlay, panel, dismiss, buttonRef]);
}

/**
 * The Explorer's one toggle (UX-5-1, DD-W168; VS Code activity bar, Docs
 * outline): a pressed/unpressed icon button at the toolbar row's left end,
 * in the same place open or closed. Its name is the panel's; the tooltip
 * says what a press does.
 */
export function IdeExplorerToggle({ toggle }: { toggle: ExplorerToggle }) {
  const t = useTranslations("creatorIde");
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          ref={toggle.buttonRef}
          variant={toggle.open ? "secondary" : "ghost"}
          size="icon"
          data-slot="ide-explorer-toggle"
          aria-label={t("explorer")}
          aria-pressed={toggle.open}
          onClick={toggle.toggle}
        >
          <PanelLeft className="size-4" aria-hidden="true" />
        </Button>
      </TooltipTrigger>
      <TooltipContent>{toggle.open ? t("hideExplorer") : t("showExplorer")}</TooltipContent>
    </Tooltip>
  );
}

/**
 * The open Explorer before the page has an id (/pages/new, BB-E-11): the
 * same card as a saved page's, so the first save moves nothing, with a note
 * (none while a saved page's IDE is loading). Closed, the column is empty.
 */
export function IdeExplorerPlaceholder({ toggle, saved = false }: { toggle: ExplorerToggle; saved?: boolean }) {
  const t = useTranslations("creatorIde");
  if (!toggle.open) return null;
  return (
    <ExplorerCard>
      {/* A saved page's Explorer is only loading: no "once it is saved" note. */}
      {!saved && (
        <Text size="sm" tone="muted">
          {t("explorerAfterSave")}
        </Text>
      )}
    </ExplorerCard>
  );
}

/**
 * The Explorer's card: the head of the workspace's first column, under the
 * sticky header and toolbar (184:159319), sticking below them as the
 * workspace scrolls.
 */
function ExplorerCard({ children }: { children: ReactNode }) {
  const t = useTranslations("creatorIde");
  return (
    <Card
      data-slot="ide-explorer"
      className="hidden lg:flex sticky top-[var(--editor-chrome-h,8rem)] w-[220px] shrink-0 self-start overflow-y-auto gap-0 py-0 h-[calc(100dvh-var(--editor-chrome-h,8rem)-2rem)]"
    >
      <Box as="nav" aria-label={t("explorer")} className="flex flex-col gap-2 p-3.5">
        <Text as="p" size="xs" tone="muted" className="font-mono uppercase tracking-wide">
          {t("explorer")}
        </Text>
        {children}
      </Box>
    </Card>
  );
}

/** The parts a template reads (D2b): one per data source, then its formulas, each with its rows. */
export function explorerParts(references: TemplateReferences): { name: string; rows: number[]; formulas: boolean }[] {
  const bySource = new Map<string, Set<number>>();
  for (const reference of references.variables) {
    const source = reference.text.split(".")[0];
    bySource.set(source, (bySource.get(source) ?? new Set()).add(reference.line));
  }
  const parts = [...bySource].map(([name, rows]) => ({ name, rows: [...rows].sort((a, b) => a - b), formulas: false }));
  const formulaRows = [...new Set(references.formulas.map((reference) => reference.line))].sort((a, b) => a - b);
  if (formulaRows.length) parts.push({ name: "", rows: formulaRows, formulas: true });
  return parts;
}

function ExplorerGroup({ label, children }: { label: string; children: React.ReactNode }) {
  const id = useId();
  return (
    <Box role="group" aria-labelledby={id} className="flex flex-col gap-1">
      <GroupLabel id={id}>{label}</GroupLabel>
      {children}
    </Box>
  );
}

/**
 * Explorer (04d 4.3, >= 1024 px), scoped to the open page (owner D2b): the
 * page itself, the boards it is live or scheduled on, the parts its template
 * reads, and snippets, with a "used by" facet beneath. It lists no other
 * page and links nowhere: the way to another page is back to Pages.
 * Collapsible (D2) from `IdeExplorerToggle` in the toolbar row.
 */
export function IdeExplorer({
  ide,
  pageId,
  references,
}: {
  ide: CreatorIdeState;
  pageId: string;
  references: TemplateReferences;
}) {
  const t = useTranslations("creatorIde");
  const page = ide.pages.find((entry) => entry.id === pageId);
  const pageName = ide.builder.snapshot?.name || page?.name || "";
  const pageState =
    ide.display === "live"
      ? t("explorerLive")
      : ide.display === "scheduled"
        ? t("explorerScheduled")
        : t("explorerNotScheduled");
  const boards = useMemo(() => {
    const byId = new Map<string, { name: string; live: boolean }>();
    for (const now of ide.showsOn.showingNow) byId.set(now.boardId, { name: now.boardName, live: true });
    for (const entry of ide.showsOn.entries) {
      if (!byId.has(entry.boardId)) byId.set(entry.boardId, { name: entry.boardName, live: false });
    }
    return [...byId].map(([id, board]) => ({ id, ...board }));
  }, [ide.showsOn]);
  const parts = useMemo(() => explorerParts(references), [references]);
  const usedBy = ide.showsOn.collections.map((entry) => entry.collection.name);

  return (
    <ExplorerCard>
      {/* UX-5-2: on a page that shows on one display (or none) the page and its
          display are the header's facts; the Explorer is then a Parts outline. */}
      {boards.length > 1 && (
        <>
          <ExplorerGroup label={t("thisPageGroup")}>
            <ListRowGroup variant="plain">
              <ListRow title={pageName} description={pageState} selected />
            </ListRowGroup>
          </ExplorerGroup>
          <ExplorerGroup label={t("boardsGroup")}>
            <ListRowGroup variant="plain">
              {boards.map((board) => (
                <ListRow
                  key={board.id}
                  title={board.name}
                  description={board.live ? t("explorerLive") : t("explorerScheduled")}
                />
              ))}
            </ListRowGroup>
          </ExplorerGroup>
        </>
      )}
      <ExplorerGroup label={t("partsGroup")}>
        {parts.length ? (
          <ListRowGroup variant="plain">
            {parts.map((part) => (
              <ListRow
                key={part.formulas ? "=" : part.name}
                title={part.formulas ? t("formulasPart") : part.name}
                description={t(part.rows.length === 1 ? "partRow" : "partRows", { rows: part.rows.join(", ") })}
              />
            ))}
          </ListRowGroup>
        ) : (
          <Text size="sm" tone="muted">
            {t("noParts")}
          </Text>
        )}
      </ExplorerGroup>
      {/* M2: Snippets is hidden while the hub has none to offer, and "not in any
          collection" is said by saying nothing. */}
      {usedBy.length > 0 && (
        <Stack className="mt-auto pt-2">
          <Text size="xs" tone="muted">
            {t("usedBy", { names: usedBy.join(", "), count: usedBy.length })}
          </Text>
        </Stack>
      )}
    </ExplorerCard>
  );
}
