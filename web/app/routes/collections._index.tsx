import {
  Badge,
  Box,
  Button,
  Card,
  EmptyState,
  Flex,
  Grid,
  PageSection,
  PageToolbar,
  Skeleton,
  Text,
} from "@fiestaboard/ui";
import { GalleryHorizontalEnd, Plus } from "lucide-react";
import { useState } from "react";

import { CollectionPageStack } from "@/components/collection-page-stack";
import { collectionScheduleSummary, formatDurationLabel, useAllSchedules } from "@/components/collection-schedule";
import { LibraryViewToggle } from "@/components/library-view-toggle";
import { useCollections, usePages } from "@/hooks/use-board";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useLocale, useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";

const VIEW_KEY = "fiestaboard_collections_view_mode";
export default function CollectionsIndex() {
  const t = useTranslations("collections");
  const tc = useTranslations("common");
  const tIde = useTranslations("creatorIde");
  const locale = useLocale();
  const { data: schedulesData } = useAllSchedules();
  const { push } = useViewTransition();
  const { data, isLoading, isError, refetch } = useCollections();
  const { data: pagesData } = usePages();
  const [viewMode, setViewMode] = useState<"grid" | "list">(() => {
    try {
      return localStorage.getItem(VIEW_KEY) === "list" ? "list" : "grid";
    } catch {
      return "grid";
    }
  });
  const changeView = (mode: "grid" | "list") => {
    setViewMode(mode);
    try {
      localStorage.setItem(VIEW_KEY, mode);
    } catch {}
  };
  const collections = data?.collections ?? [];
  const pages = pagesData?.pages ?? [];
  return (
    <>
      <PageToolbar
        className="!py-3 px-4 sm:px-6"
        left={
          <Flex align="center" gap="3">
            <LibraryViewToggle value={viewMode} onValueChange={changeView} />
            <Text size="xs" tone="muted">
              {t("libraryCount", { count: collections.length })}
            </Text>
          </Flex>
        }
        right={
          <Button
            variant="brand"
            size="sm"
            onClick={() => push("/collections/new")}
            {...anchorProps("collections.new")}
          >
            <Plus className="h-4 w-4 mr-1" />
            {t("newCollection")}
          </Button>
        }
      />
      <PageSection
        className="px-4 pt-0 pb-4 sm:px-6 [&:not(:first-child)]:border-t-0"
        {...anchorProps("collections.root")}
      >
        {isLoading ? (
          <Skeleton className="h-48 w-full" />
        ) : isError ? (
          <EmptyState
            icon={GalleryHorizontalEnd}
            title={t("loadFailed")}
            action={
              <Button variant="outline" onClick={() => void refetch()}>
                {t("retryButton")}
              </Button>
            }
          />
        ) : collections.length === 0 ? (
          <Box className="py-8">
            <EmptyState
              icon={GalleryHorizontalEnd}
              title={t("noCollectionsTitle")}
              description={t("noCollectionsDescription")}
              action={
                <Button variant="brand" onClick={() => push("/collections/new")}>
                  <Plus className="mr-1 h-4 w-4" />
                  {t("createFirstCollection")}
                </Button>
              }
            />
          </Box>
        ) : (
          <Grid
            cols="1"
            gap={viewMode === "grid" ? "4" : "2"}
            className={viewMode === "grid" ? "sm:grid-cols-2 xl:grid-cols-3" : ""}
          >
            {collections.map((collection) => {
              const modeLabel = t(
                collection.selection_mode === "time"
                  ? "modeTimeLabel"
                  : collection.selection_mode === "random"
                    ? "modeRandomLabel"
                    : "modeVariableLabel",
              );
              // Figma 342:187593 meta. No display name leads it: a Collection is not
              // bound to a board (DD-W82).
              const pageCount = tc("pageCount", { count: collection.page_ids.length });
              const meta =
                collection.selection_mode === "variable"
                  ? t("ruleCount", { count: collection.variable?.rules.length ?? 0 })
                  : collection.selection_mode === "random"
                    ? `${pageCount} · ${t("everyDuration", {
                        duration: formatDurationLabel(collection.random?.interval_seconds ?? 30, locale),
                      })}`
                    : `${pageCount} · ${t("rotationTotal", {
                        duration: formatDurationLabel(
                          collection.time.interval_seconds * collection.page_ids.length,
                          locale,
                        ),
                      })}`;
              const schedule = collectionScheduleSummary(collection.id, schedulesData?.schedules, t, tIde, locale);
              return (
                <Card
                  key={collection.id}
                  {...anchorProps(`collection.${collection.id}`)}
                  className="relative min-w-0 gap-0 overflow-hidden p-0 hover:border-brand/50 hover:bg-accent focus-within:ring-2 focus-within:ring-ring"
                >
                  {viewMode === "grid" && <CollectionPageStack collection={collection} pages={pages} />}
                  <button
                    type="button"
                    data-section-item={collection.id}
                    className="min-w-0 px-3.5 py-3 text-left outline-none after:absolute after:inset-0 after:rounded-xl"
                    onClick={() => push(`/collections/${encodeURIComponent(collection.id)}`)}
                  >
                    <Flex align="center" gap="2" className="min-w-0">
                      <Text as="span" size="sm" weight="semibold" className="truncate">
                        {collection.name}
                      </Text>
                      <Badge variant="outline">{modeLabel}</Badge>
                    </Flex>
                    <Text size="xs" tone="muted" className="mt-1.5">
                      {meta}
                    </Text>
                    <Text size="xs" tone="muted" className="mt-1">
                      {schedule ? t("cardSchedule", { schedule }) : t("notScheduled")}
                    </Text>
                  </button>
                </Card>
              );
            })}
          </Grid>
        )}
      </PageSection>
    </>
  );
}
