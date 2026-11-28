"use client";

import { Box, Button, Card, Flex, ListRow, ListRowGroup, Stack, Text } from "@fiestaboard/ui";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { type ReactNode, type Ref, useEffect, useId, useMemo, useRef } from "react";

import { useTranslations } from "@/i18n/translations";
import type { DeviceType } from "@/lib/api";
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
 * The Explorer's open state for this board kind (D2) with its two buttons'
 * refs: focus follows a toggle to the counterpart button, so a keyboard
 * reader isn't dropped on <body>.
 */
export function useExplorerToggle(kind: DeviceType) {
  const [open, setOpen] = useExplorerOpen(kind);
  const showRef = useRef<HTMLButtonElement>(null);
  const hideRef = useRef<HTMLButtonElement>(null);
  const toggled = useRef(false);
  useEffect(() => {
    if (!toggled.current) return;
    toggled.current = false;
    (open ? hideRef : showRef).current?.focus();
  }, [open]);
  const toggle = (next: boolean) => {
    toggled.current = true;
    setOpen(next);
  };
  return { open, show: () => toggle(true), hide: () => toggle(false), showRef, hideRef };
}

export type ExplorerToggle = ReturnType<typeof useExplorerToggle>;

/**
 * The Explorer column before the page has an id (/pages/new, BB-E-11): the
 * same frame as a saved page's, so the first save moves nothing. Open, it is
 * the Explorer card with a note (none while a saved page's IDE is loading);
 * closed, the Show Explorer button.
 */
export function IdeExplorerPlaceholder({ toggle, saved = false }: { toggle: ExplorerToggle; saved?: boolean }) {
  const t = useTranslations("creatorIde");
  if (!toggle.open) return <IdeExplorerShow onShow={toggle.show} buttonRef={toggle.showRef} />;
  return (
    <ExplorerCard onHide={toggle.hide} hideRef={toggle.hideRef}>
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
function ExplorerCard({
  onHide,
  hideRef,
  children,
}: {
  onHide?: () => void;
  hideRef?: Ref<HTMLButtonElement>;
  children: ReactNode;
}) {
  const t = useTranslations("creatorIde");
  return (
    <Card
      data-slot="ide-explorer"
      className="hidden lg:flex sticky top-[var(--editor-chrome-h,8rem)] w-[220px] shrink-0 self-start overflow-y-auto gap-0 py-0 h-[calc(100dvh-var(--editor-chrome-h,8rem)-2rem)]"
    >
      <Box as="nav" aria-label={t("explorer")} className="flex flex-col gap-2 p-3.5">
        <Flex align="center" justify="between" gap="2">
          <Text as="p" size="xs" tone="muted" className="font-mono uppercase tracking-wide">
            {t("explorer")}
          </Text>
          {onHide && (
            <Button
              ref={hideRef}
              variant="ghost"
              size="icon"
              className="-my-1.5 -mr-1.5"
              aria-label={t("hideExplorer")}
              aria-expanded={true}
              onClick={onHide}
            >
              <PanelLeftClose className="size-4" aria-hidden="true" />
            </Button>
          )}
        </Flex>
        {children}
      </Box>
    </Card>
  );
}

/**
 * The closed Explorer (D2, BB-E-3): one button at the head of the column it
 * gives back to the editor.
 */
export function IdeExplorerShow({ onShow, buttonRef }: { onShow: () => void; buttonRef?: Ref<HTMLButtonElement> }) {
  const t = useTranslations("creatorIde");
  return (
    <Box
      data-slot="ide-explorer-closed"
      className="hidden lg:flex sticky top-[var(--editor-chrome-h,8rem)] shrink-0 self-start"
    >
      <Button
        ref={buttonRef}
        variant="ghost"
        size="icon"
        aria-label={t("showExplorer")}
        aria-expanded={false}
        onClick={onShow}
      >
        <PanelLeftOpen className="size-4" aria-hidden="true" />
      </Button>
    </Box>
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
 * Collapsible (D2): `onHide` closes it to `IdeExplorerShow`.
 */
export function IdeExplorer({
  ide,
  pageId,
  references,
  onHide,
  hideRef,
}: {
  ide: CreatorIdeState;
  pageId: string;
  references: TemplateReferences;
  onHide?: () => void;
  hideRef?: Ref<HTMLButtonElement>;
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
    <ExplorerCard onHide={onHide} hideRef={hideRef}>
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
