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

/** A resting, bounded stack; this component is never mounted in list mode. */
export function CollectionPageStack({ collection, pages }: { collection: Collection; pages: Page[] }) {
  const { data: settings } = useBoardSettings();
  const { currentBoardId } = useCurrentBoard();
  const members = useMemo(
    () =>
      collection.page_ids.slice(0, 3).flatMap((id) => {
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
      className="relative h-40 w-full overflow-hidden pointer-events-none [&_button]:hidden"
    >
      {isLoading ? (
        <Skeleton className="h-28 w-full rounded-md" />
      ) : (
        members.map(({ page, board, model }, index) => {
          const preview = previews?.[page.id];
          return (
            <Box
              key={page.id}
              className="absolute left-0 right-6 top-0 overflow-hidden rounded-lg border bg-background p-2 shadow-sm"
              style={{
                transform: `translate(${index * 10}px, ${index * 13}px) rotate(${index * 2}deg)`,
                transformOrigin: "center",
                zIndex: members.length - index,
              }}
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
