"use client";

import { Badge, EmptyState, Flex, Stack, Tabs, TabsContent, TabsList, TabsTrigger, Text } from "@fiestaboard/ui";
import { Check, FileText, GalleryHorizontalEnd, LayoutTemplate } from "lucide-react";

import { BoardSizeIndicator } from "@/components/board-size-indicator";
import { useCurrentBoard } from "@/components/current-board-context";
import { useTranslations } from "@/i18n/translations";
import type { Collection } from "@/lib/api";
import { isCollectionId } from "@/lib/api";
import { pagesCompatibleWithBoard } from "@/lib/board-dimensions";

interface Page {
  id: string;
  name: string;
  type?: string;
  /** Board geometry for size badges/filtering; pages without it act as flagship. */
  device_type?: string;
  notes_wide?: number;
  notes_tall?: number;
}

interface PagePickerDialogProps {
  pages: Page[];
  collections?: Collection[];
  selectedPageId: string | null;
  onSelect: (pageId: string | null) => void;
  allowNone?: boolean;
  /** Show only pages whose size matches the current board (issue #1249). */
  filterByCurrentBoardSize?: boolean;
}

/**
 * Simple page/collection picker for selecting (not editing) pages or collections.
 * Used for default page selection in schedule settings and schedule entry form.
 */
export function PagePickerDialog({
  pages,
  collections = [],
  selectedPageId,
  onSelect,
  allowNone = false,
  filterByCurrentBoardSize = false,
}: PagePickerDialogProps) {
  const t = useTranslations("pagePickerDialog");
  const { currentBoard } = useCurrentBoard();
  // Size filter (issue #1249): keep the current selection visible even when it
  // no longer fits, so an existing choice never silently disappears.
  const visiblePages =
    filterByCurrentBoardSize && currentBoard
      ? pages.filter((p) => p.id === selectedPageId || pagesCompatibleWithBoard(p, currentBoard))
      : pages;
  const hasCollections = collections.length > 0;
  const defaultTab = selectedPageId && isCollectionId(selectedPageId) ? "collections" : "pages";

  const noneOption = allowNone && (
    <button
      aria-pressed={selectedPageId === null}
      onClick={() => onSelect(null)}
      className={`w-full flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
        selectedPageId === null ? "border-brand bg-muted/50" : ""
      }`}
    >
      <Text as="span" weight="medium">
        {t("noneNoDefault")}
      </Text>
      {selectedPageId === null && <Check className="h-4 w-4 text-brand" aria-hidden="true" />}
    </button>
  );

  const pagesList = (
    <Stack gap="2" role="listbox" aria-label={t("pagesAriaLabel")}>
      {visiblePages.map((page) => (
        <button
          key={page.id}
          role="option"
          aria-selected={selectedPageId === page.id}
          onClick={() => onSelect(page.id)}
          className={`w-full flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            selectedPageId === page.id ? "border-brand bg-muted/50" : ""
          }`}
        >
          <Flex align="center" gap="2">
            <Text as="span" weight="medium">
              {page.name}
            </Text>
            {page.type && (
              <Badge variant="secondary" className="text-[10px]">
                {page.type}
              </Badge>
            )}
            {page.device_type && (
              <BoardSizeIndicator
                deviceType={page.device_type}
                notesWide={page.notes_wide}
                notesTall={page.notes_tall}
              />
            )}
          </Flex>
          {selectedPageId === page.id && <Check className="h-4 w-4 text-brand" aria-hidden="true" />}
        </button>
      ))}
    </Stack>
  );

  const collectionsList = (
    <Stack gap="2" role="listbox" aria-label={t("collectionsAriaLabel")}>
      {collections.map((collection) => (
        <button
          key={collection.id}
          role="option"
          aria-selected={selectedPageId === collection.id}
          onClick={() => onSelect(collection.id)}
          className={`w-full flex items-center justify-between p-3 border rounded-lg hover:bg-muted/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
            selectedPageId === collection.id ? "border-brand bg-muted/50" : ""
          }`}
        >
          <Flex align="center" gap="2">
            <GalleryHorizontalEnd className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
            <Text as="span" weight="medium">
              {collection.name}
            </Text>
            <Badge variant="secondary" className="text-[10px]">
              {t("pageCount", { count: collection.page_ids.length })}
            </Badge>
          </Flex>
          {selectedPageId === collection.id && <Check className="h-4 w-4 text-brand" aria-hidden="true" />}
        </button>
      ))}
    </Stack>
  );

  if (!hasCollections) {
    return (
      <Stack gap="2">
        {noneOption}
        {visiblePages.length === 0 ? (
          <EmptyState icon={FileText} title={t("noPagesTitle")} description={t("noPagesDescription")} />
        ) : (
          pagesList
        )}
      </Stack>
    );
  }

  return (
    <Stack gap="2">
      {noneOption}
      <Tabs defaultValue={defaultTab}>
        <TabsList className="w-full">
          <TabsTrigger value="pages" className="flex-1 gap-1.5">
            <LayoutTemplate className="h-4 w-4" aria-hidden="true" />
            {t("pagesTab", { count: visiblePages.length })}
          </TabsTrigger>
          <TabsTrigger value="collections" className="flex-1 gap-1.5">
            <GalleryHorizontalEnd className="h-4 w-4" aria-hidden="true" />
            {t("collectionsTab", { count: collections.length })}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="pages">
          {visiblePages.length === 0 ? (
            <EmptyState icon={FileText} title={t("noPagesTitle")} description={t("noPagesDescription")} />
          ) : (
            pagesList
          )}
        </TabsContent>
        <TabsContent value="collections">{collectionsList}</TabsContent>
      </Tabs>
    </Stack>
  );
}
