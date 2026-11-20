"use client";

import { Box, Button, Card, Flex, ListRow, ListRowGroup, Stack, Text } from "@fiestaboard/ui";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { type Ref, useId, useMemo } from "react";

import { useTranslations } from "@/i18n/translations";
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
 * The closed Explorer (D2, BB-E-3): one button at the head of the column it
 * gives back to the editor.
 */
export function IdeExplorerShow({ onShow, buttonRef }: { onShow: () => void; buttonRef?: Ref<HTMLButtonElement> }) {
  const t = useTranslations("creatorIde");
  return (
    <Box data-slot="ide-explorer-closed" className="hidden lg:flex shrink-0 self-start my-4 ml-3">
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
    <Card
      data-slot="ide-explorer"
      className="hidden lg:flex w-[220px] shrink-0 overflow-y-auto gap-0 py-0 my-4 ml-3 self-start max-h-[calc(100%-2rem)]"
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
        <ExplorerGroup label={t("thisPageGroup")}>
          <ListRowGroup variant="plain">
            <ListRow title={pageName} description={pageState} selected />
          </ListRowGroup>
        </ExplorerGroup>
        <ExplorerGroup label={t("boardsGroup")}>
          {boards.length ? (
            <ListRowGroup variant="plain">
              {boards.map((board) => (
                <ListRow
                  key={board.id}
                  title={board.name}
                  description={board.live ? t("explorerLive") : t("explorerScheduled")}
                />
              ))}
            </ListRowGroup>
          ) : (
            <Text size="sm" tone="muted">
              {t("noBoards")}
            </Text>
          )}
        </ExplorerGroup>
        <ExplorerGroup label={t("partsGroup")}>
          {parts.length ? (
            <ListRowGroup variant="plain">
              {parts.map((part) => (
                <ListRow
                  key={part.formulas ? "=" : part.name}
                  title={part.formulas ? t("formulasPart") : part.name}
                  description={t("partRows", { count: part.rows.length, rows: part.rows.join(", ") })}
                />
              ))}
            </ListRowGroup>
          ) : (
            <Text size="sm" tone="muted">
              {t("noParts")}
            </Text>
          )}
        </ExplorerGroup>
        <ExplorerGroup label={t("snippetsGroup")}>
          <Text size="sm" tone="muted">
            {t("snippetsUnavailable")}
          </Text>
        </ExplorerGroup>
        <Stack className="mt-auto pt-2">
          <Text size="xs" tone="muted">
            {usedBy.length ? t("usedBy", { names: usedBy.join(", "), count: usedBy.length }) : t("usedByNone")}
          </Text>
        </Stack>
      </Box>
    </Card>
  );
}
