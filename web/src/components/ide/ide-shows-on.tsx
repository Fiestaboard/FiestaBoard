"use client";

import { Box, Button, Flex, InspectorRow, List, ListItem, ListRow, Stack, Text } from "@fiestaboard/ui";
import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useId } from "react";

import { nudgeDisplay, useRefreshHomeStatus } from "@/components/home/use-home-data";
import { useLocale, useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { pagesCompatibleWithBoard } from "@/lib/board-dimensions";

import { formatDays, formatWallTime, formatWindow } from "./ide-format";
import { IdeWeek } from "./ide-timeline";
import type { CreatorIdeState } from "./use-creator-ide";

/** A Shows on group: a mono caps heading over its rows (DISPLAY, SCHEDULE, COLLECTIONS). */
function ShowsOnGroup({ label, children }: { label: string; children: ReactNode }) {
  const id = useId();
  return (
    <Box role="group" aria-labelledby={id} className="flex flex-col">
      <Text as="p" id={id} size="xs" tone="muted" className="font-mono uppercase tracking-wide">
        {label}
      </Text>
      <List gap="0" role="list">
        {children}
      </List>
    </Box>
  );
}

/**
 * D3 (DD-W159): the one control for the page's target display. A display of
 * the page's size retargets the preview and mirror; another size cannot take
 * the template as is, so it offers "Make a copy sized for X" (Figma's Page-tab row).
 */
function IdeDisplayPicker({
  ide,
  onRetarget,
  onCopyFor,
}: {
  ide: CreatorIdeState;
  onRetarget: (boardId: string) => void;
  onCopyFor: (boardId: string) => void;
}) {
  const t = useTranslations("creatorIde");
  const tq = useTranslations("ideQuiet");
  const page = ide.builder.snapshot;
  if (!page || !ide.boards.length) return null;
  return (
    <Box data-slot="ide-display-picker">
      <ShowsOnGroup label={tq("displayGroup")}>
        {ide.boards.map((board) => {
          if (board.id === ide.pageBoardId) {
            // The page's own display: a fact, not an action.
            return (
              <ListItem key={board.id}>
                <ListRow
                  title={board.name}
                  meta={t("thisDisplay")}
                  aria-current="true"
                  variant="plain"
                  className="border-b border-border px-0"
                />
              </ListItem>
            );
          }
          const fits = pagesCompatibleWithBoard(page, board);
          return (
            <ListItem key={board.id}>
              <InspectorRow
                title={board.name}
                detail={fits ? tq("displayRetarget") : tq("copySizedFor", { board: board.name })}
                chevron={!fits}
                onPress={() => (fits ? onRetarget(board.id) : onCopyFor(board.id))}
              />
            </ListItem>
          );
        })}
      </ShowsOnGroup>
    </Box>
  );
}

/**
 * W-2: a running Show now (the display's temporary override) leads Shows on,
 * with its end and a Stop, so the page's live state has one place to end it.
 */
function IdeShowingNow({ ide }: { ide: CreatorIdeState }) {
  const tq = useTranslations("ideQuiet");
  const locale = useLocale();
  const queryClient = useQueryClient();
  const refresh = useRefreshHomeStatus();
  const stop = useMutation({
    mutationFn: (boardId: string) => api.clearTemporaryOverride(boardId),
    onSuccess: (_result, boardId) => {
      nudgeDisplay(boardId);
      refresh();
      void queryClient.invalidateQueries({ queryKey: ["ide", "active"] });
    },
  });
  const held = ide.showsOn.showingNow.filter((showing) => showing.override);
  if (!held.length) return null;
  return (
    <ShowsOnGroup label={tq("showingNowGroup")}>
      {held.map((showing) => {
        const until = formatWallTime(showing.until, locale);
        return (
          <ListItem key={showing.boardId}>
            <ListRow
              variant="plain"
              className="border-b border-border px-0"
              title={
                until
                  ? tq("overrideUntil", { board: showing.boardName, time: until })
                  : tq("overrideUntilCancel", { board: showing.boardName })
              }
              trailing={
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={stop.isPending}
                  onClick={() => stop.mutate(showing.boardId)}
                >
                  {tq("stopShowing")}
                </Button>
              }
            />
          </ListItem>
        );
      })}
    </ShowsOnGroup>
  );
}

/**
 * Shows on (04d 1.6b, H8): when and where this page shows. Schedule entries
 * (direct or through a collection) with "Now" from the hub's instant answer,
 * and each collection's rule dry run at this moment.
 */
export function IdeShowsOn({
  ide,
  pageId,
  showWeek,
  onNavigate,
  onRetarget,
  onCopyFor,
}: {
  ide: CreatorIdeState;
  pageId: string;
  showWeek: boolean;
  onNavigate: (href: string) => void;
  onRetarget: (boardId: string) => void;
  onCopyFor: (boardId: string) => void;
}) {
  const t = useTranslations("creatorIde");
  const tq = useTranslations("ideQuiet");
  const locale = useLocale();
  const dryRuns = useQueries({
    queries: ide.showsOn.collections.map(({ collection }) => ({
      queryKey: ["ide", "dry-run", collection.id],
      queryFn: () => api.dryRunCollection(collection.id, {}),
      refetchInterval: 60_000,
      retry: false,
    })),
  });
  const pageName = (id: string | null | undefined) => ide.pages.find((page) => page.id === id)?.name;
  const empty = !ide.showsOn.entries.length && !ide.showsOn.collections.length && !ide.showsOn.showingNow.length;

  return (
    <Stack gap="3" data-slot="ide-shows-on">
      <IdeShowingNow ide={ide} />
      <IdeDisplayPicker ide={ide} onRetarget={onRetarget} onCopyFor={onCopyFor} />
      {showWeek && <IdeWeek ide={ide} />}
      {empty && (
        <Text size="sm" tone="muted">
          {t("showsOnEmpty")}
        </Text>
      )}
      {ide.showsOn.entries.length > 0 && (
        <ShowsOnGroup label={tq("scheduleGroup")}>
          {ide.showsOn.entries.map((entry) => (
            <ListItem key={entry.schedule.id}>
              <InspectorRow
                title={`${formatDays(entry.schedule, t, locale)} ${formatWindow(entry.schedule, locale)}`}
                detail={
                  entry.collection
                    ? t("entryThroughCollection", { board: entry.boardName, name: entry.collection.name })
                    : t("entryDirect", { board: entry.boardName })
                }
                value={entry.now ? t("now") : entry.schedule.enabled ? undefined : t("entryOff")}
                chevron
                onPress={() => onNavigate("/schedule")}
              />
            </ListItem>
          ))}
        </ShowsOnGroup>
      )}
      {ide.showsOn.collections.length > 0 && (
        <ShowsOnGroup label={tq("collectionsGroup")}>
          {ide.showsOn.collections.map(({ collection, position, size }, index) => {
            const run = dryRuns[index]?.data;
            const nowShowing = run?.page_id;
            return (
              <ListItem key={collection.id}>
                <InspectorRow
                  title={collection.name}
                  detail={[
                    t("collectionPlace", { position, size }),
                    run
                      ? nowShowing === pageId
                        ? t("ruleShowsThis")
                        : t("ruleShowsOther", { name: pageName(nowShowing) ?? t("nothing") })
                      : null,
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                  chevron
                  onPress={() => onNavigate(`/collections/${encodeURIComponent(collection.id)}`)}
                />
              </ListItem>
            );
          })}
        </ShowsOnGroup>
      )}
      {/* Copies are per display in the Display group above (D3); no third entry point here. */}
      <Flex gap="2" className="flex-wrap">
        <Button
          variant="secondary"
          onClick={() => onNavigate(`/schedule?prefill_page_id=${encodeURIComponent(pageId)}`)}
        >
          {t("addEntry")}
        </Button>
        <Button variant="outline" onClick={() => onNavigate("/collections")}>
          {t("addToCollection")}
        </Button>
      </Flex>
    </Stack>
  );
}
