import { type BoardCellGrid, Box, Skeleton } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { useCurrentBoard } from "@/components/current-board-context";
import { DevicePreview } from "@/components/device-preview";
import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { getEffectiveBoardColor, useBoardSettings } from "@/hooks/use-board";
import type { Collection, Page, PagePreviewResponse } from "@/lib/api";
import { api } from "@/lib/api";
import { boardForShape, isLedModel, resolveBoardModel } from "@/lib/device-preview";

/**
 * The card's cover: the Collection's first page as one full-bleed board across
 * the top of the card (Figma 342:187593), not a stack of tilted cards in an
 * inset box (BB-FP-20). Never mounted in list mode.
 */
export function CollectionPageStack({ collection, pages }: { collection: Collection; pages: Page[] }) {
  const { data: settings } = useBoardSettings();
  const { currentBoardId } = useCurrentBoard();
  const members = useMemo(
    () =>
      collection.page_ids.slice(0, 1).flatMap((id) => {
        const page = pages.find((candidate) => candidate.id === id);
        if (!page) return [];
        const board = boardForShape(settings?.boards, [currentBoardId], page);
        const model = resolveBoardModel(board);
        return [{ page, board, model, boardId: board && isLedModel(model) ? board.id : undefined }];
      }),
    [collection.page_ids, pages, settings?.boards, currentBoardId],
  );
  const { data: previews, isLoading } = useQuery({
    queryKey: ["collection-previews", members.map(({ page, boardId }) => [page.id, page.updated_at, boardId])],
    enabled: members.length > 0,
    staleTime: 60_000,
    queryFn: async () => {
      const groups = new Map<string | undefined, string[]>();
      for (const { page, boardId } of members) groups.set(boardId, [...(groups.get(boardId) ?? []), page.id]);
      const batches = await Promise.all([...groups].map(([boardId, ids]) => api.previewPagesBatch(ids, boardId)));
      const result: Record<string, PagePreviewResponse> = {};
      for (const batch of batches)
        for (const [id, preview] of Object.entries(batch.previews)) {
          if (preview.available) result[id] = preview;
        }
      return result;
    },
  });
  return (
    <Box
      data-testid="collection-page-stack"
      aria-hidden="true"
      inert
      className="w-full overflow-hidden pointer-events-none [&_button]:hidden"
    >
      {isLoading ? (
        <Skeleton className="h-36 w-full rounded-none" />
      ) : (
        members.map(({ page, board, model }) => {
          const preview = previews?.[page.id];
          return (
            // Edge to edge: the board's own housing colour fills the card's top, with no
            // shadow margin around a framed board (Figma 342:187593).
            <Box
              key={page.id}
              data-slot="collection-cover-board"
              className={
                getEffectiveBoardColor(settings) === "white"
                  ? "w-full bg-board-bezel-light p-3"
                  : "w-full bg-board-bezel-dark p-3"
              }
            >
              <DevicePreview
                model={model}
                ledLayout={board?.led_layout}
                message={preview?.message}
                cells={preview?.cells as BoardCellGrid | undefined}
                layers={preview?.layers}
                size="sm"
              >
                <ScaledBoardDisplay
                  // Decorative and inert: a fit picture, never a scroll region.
                  thumbnail
                  bezel={false}
                  isStatic
                  message={preview?.message ?? null}
                  boardType={getEffectiveBoardColor(settings)}
                  deviceType={page.device_type ?? "flagship"}
                  notesWide={page.notes_wide}
                  notesTall={page.notes_tall}
                  gridRows={page.grid_rows ?? undefined}
                  gridCols={page.grid_cols ?? undefined}
                  size="sm"
                />
              </DevicePreview>
            </Box>
          );
        })
      )}
    </Box>
  );
}
