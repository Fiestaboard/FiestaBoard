"use client";

import { Box, Button, Card, Flex, Input, ListRow, ListRowGroup, Stack, Text } from "@fiestaboard/ui";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { type Ref, useId, useMemo, useState } from "react";
import { Link } from "react-router";

import { useTranslations } from "@/i18n/translations";

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
        title={t("showExplorer")}
        onClick={onShow}
      >
        <PanelLeftOpen className="size-4" aria-hidden="true" />
      </Button>
    </Box>
  );
}

/**
 * Explorer (04d 4.3, >= 1024 px): this hub's pages, collections and
 * snippets, with the open page selected and a "used by" facet beneath.
 * Collapsible (D2): `onHide` closes it to `IdeExplorerShow`.
 */
export function IdeExplorer({
  ide,
  pageId,
  onHide,
  hideRef,
}: {
  ide: CreatorIdeState;
  pageId: string;
  onHide?: () => void;
  hideRef?: Ref<HTMLButtonElement>;
}) {
  const t = useTranslations("creatorIde");
  const [filter, setFilter] = useState("");
  const pagesLabel = useId();
  const collectionsLabel = useId();
  const snippetsLabel = useId();
  const needle = filter.trim().toLocaleLowerCase();
  const pages = useMemo(
    () => ide.pages.filter((page) => !needle || page.name.toLocaleLowerCase().includes(needle)),
    [ide.pages, needle],
  );
  const collections = ide.collections.filter(
    (collection) => !needle || collection.name.toLocaleLowerCase().includes(needle),
  );
  const describePage = (id: string) => {
    if (id === pageId) {
      if (ide.display === "live") return t("explorerLive");
      return ide.display === "scheduled" ? t("explorerScheduled") : t("explorerNotScheduled");
    }
    const viaCollection = new Set(ide.collections.filter((c) => c.page_ids.includes(id)).map((c) => c.id));
    const scheduled = ide.schedules.some(
      (entry) => entry.enabled && (entry.page_id === id || viaCollection.has(entry.page_id)),
    );
    return scheduled ? t("explorerScheduled") : t("explorerNotScheduled");
  };
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
              title={t("hideExplorer")}
              onClick={onHide}
            >
              <PanelLeftClose className="size-4" aria-hidden="true" />
            </Button>
          )}
        </Flex>
        <Input
          type="search"
          value={filter}
          onChange={(event) => setFilter(event.target.value)}
          placeholder={t("filterPages")}
          aria-label={t("filterPages")}
          className="h-8"
        />
        <GroupLabel id={pagesLabel}>{t("pagesGroup")}</GroupLabel>
        {pages.length ? (
          <ListRowGroup variant="plain" aria-labelledby={pagesLabel}>
            {pages.map((page) => (
              <ListRow
                key={page.id}
                title={page.name}
                description={describePage(page.id)}
                selected={page.id === pageId}
                render={<Link to={`/pages/edit/${encodeURIComponent(page.id)}`} />}
              />
            ))}
          </ListRowGroup>
        ) : (
          <Text size="sm" tone="muted">
            {t("noMatches")}
          </Text>
        )}
        <GroupLabel id={collectionsLabel}>{t("collectionsGroup")}</GroupLabel>
        {collections.length ? (
          <ListRowGroup variant="plain" aria-labelledby={collectionsLabel}>
            {collections.map((collection) => (
              <ListRow
                key={collection.id}
                title={collection.name}
                description={t("collectionPages", { count: collection.page_ids.length })}
                render={<Link to={`/collections/${encodeURIComponent(collection.id)}`} />}
              />
            ))}
          </ListRowGroup>
        ) : (
          <Text size="sm" tone="muted">
            {needle ? t("noMatches") : t("noCollections")}
          </Text>
        )}
        <GroupLabel id={snippetsLabel}>{t("snippetsGroup")}</GroupLabel>
        <Text size="sm" tone="muted" aria-describedby={snippetsLabel}>
          {t("snippetsUnavailable")}
        </Text>
        <Stack className="mt-auto pt-2">
          <Text size="xs" tone="muted">
            {usedBy.length ? t("usedBy", { names: usedBy.join(", "), count: usedBy.length }) : t("usedByNone")}
          </Text>
        </Stack>
      </Box>
    </Card>
  );
}
