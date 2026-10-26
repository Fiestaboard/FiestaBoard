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
import { Clock, GalleryHorizontalEnd, LayoutGrid, List, Plus, Shuffle, Sigma } from "lucide-react";
import { useState } from "react";

import { formatInterval } from "@/components/collection-form";
import { CollectionPageStack } from "@/components/collection-page-stack";
import { useCollections, usePages } from "@/hooks/use-board";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";

const VIEW_KEY = "fiestaboard_collections_view_mode";
export default function CollectionsIndex() {
  const t = useTranslations("collections");
  const tc = useTranslations("common");
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
            <Flex className="rounded-md border" role="group" aria-label={t("viewModeLabel")}>
              <Button
                size="sm"
                variant={viewMode === "grid" ? "secondary" : "ghost"}
                className="h-8 w-8 p-0 rounded-r-none"
                aria-label={t("gridView")}
                aria-pressed={viewMode === "grid"}
                onClick={() => changeView("grid")}
              >
                <LayoutGrid className="h-4 w-4" />
              </Button>
              <Button
                size="sm"
                variant={viewMode === "list" ? "secondary" : "ghost"}
                className="h-8 w-8 p-0 rounded-l-none"
                aria-label={t("listView")}
                aria-pressed={viewMode === "list"}
                onClick={() => changeView("list")}
              >
                <List className="h-4 w-4" />
              </Button>
            </Flex>
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
              const Icon =
                collection.selection_mode === "time" ? Clock : collection.selection_mode === "random" ? Shuffle : Sigma;
              const modeLabel = t(
                collection.selection_mode === "time"
                  ? "modeTimeLabel"
                  : collection.selection_mode === "random"
                    ? "modeRandomLabel"
                    : "modeVariableLabel",
              );
              const summary =
                collection.selection_mode === "variable"
                  ? t("variableModeBadge", { count: collection.variable?.rules.length ?? 0 })
                  : `${formatInterval(collection.selection_mode === "random" ? (collection.random?.interval_seconds ?? 30) : collection.time.interval_seconds)} ${t("perPageShort")}`;
              return (
                <Card
                  key={collection.id}
                  {...anchorProps(`collection.${collection.id}`)}
                  className="relative min-w-0 gap-3 p-4 hover:border-brand/50 hover:bg-accent focus-within:ring-2 focus-within:ring-ring"
                >
                  <button
                    type="button"
                    data-section-item={collection.id}
                    className="text-left min-w-0 outline-none after:absolute after:inset-0 after:rounded-xl"
                    onClick={() => push(`/collections/${encodeURIComponent(collection.id)}`)}
                  >
                    <Flex align="center" gap="3" className="min-w-0">
                      <GalleryHorizontalEnd className="h-4 w-4 shrink-0 text-muted-foreground" />
                      <Box className="min-w-0 flex-1">
                        <Text as="span" weight="medium" className="block truncate">
                          {collection.name}
                        </Text>
                        <Text size="xs" tone="muted">
                          {tc("pageCount", { count: collection.page_ids.length })} · {summary}
                        </Text>
                      </Box>
                      <Icon className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    </Flex>
                  </button>
                  {viewMode === "grid" && <CollectionPageStack collection={collection} pages={pages} />}
                  {viewMode === "grid" && (
                    <Flex align="center" gap="2">
                      <Badge variant="secondary" className="text-xs">
                        {modeLabel}
                      </Badge>
                      {collection.selection_mode === "variable" && (
                        <Badge variant="outline" className="text-xs">
                          {t("betaBadge")}
                        </Badge>
                      )}
                    </Flex>
                  )}
                </Card>
              );
            })}
          </Grid>
        )}
      </PageSection>
    </>
  );
}
