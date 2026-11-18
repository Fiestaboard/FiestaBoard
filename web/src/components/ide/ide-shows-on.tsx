"use client";

import { Button, Flex, InspectorRow, List, ListItem, Stack, Text } from "@fiestaboard/ui";
import { useQueries } from "@tanstack/react-query";

import { useLocale, useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

import { formatDays, formatWindow } from "./ide-format";
import { IdeWeek } from "./ide-timeline";
import type { CreatorIdeState } from "./use-creator-ide";

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
  onMakeCopy,
}: {
  ide: CreatorIdeState;
  pageId: string;
  showWeek: boolean;
  onNavigate: (href: string) => void;
  onMakeCopy: () => void;
}) {
  const t = useTranslations("creatorIde");
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
  const empty = !ide.showsOn.entries.length && !ide.showsOn.collections.length;

  return (
    <Stack gap="3" data-slot="ide-shows-on">
      {showWeek && <IdeWeek ide={ide} />}
      {empty ? (
        <Text size="sm" tone="muted">
          {t("showsOnEmpty")}
        </Text>
      ) : (
        <List gap="0" role="list">
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
        </List>
      )}
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
        <Button variant="ghost" onClick={onMakeCopy}>
          {t("makeCopyShort")}
        </Button>
      </Flex>
    </Stack>
  );
}
