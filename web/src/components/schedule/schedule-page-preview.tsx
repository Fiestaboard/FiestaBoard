import { Text } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";

import { BoardViewport } from "@/components/board-viewport";
import { useCurrentBoard } from "@/components/current-board-context";
import { DevicePreview } from "@/components/device-preview";
import { api, isCollectionId, type Page } from "@/lib/api";
import { resolveBoardModel } from "@/lib/device-preview";
/** Render only the identified page in this evidence context; null means no winner. */
export function SchedulePagePreview({
  pageId,
  pages,
  at,
  boardId,
  values,
  missing,
  label,
}: {
  pageId: string | null | undefined;
  pages: Page[];
  at: string;
  boardId?: string;
  values?: Record<string, unknown>;
  missing?: string[];
  label: string;
}) {
  const { boards, currentBoard } = useCurrentBoard();
  const target = boardId ? boards?.find((board) => board.id === boardId) : currentBoard;
  const model = resolveBoardModel(target);
  const collection = useQuery({
    queryKey: ["schedule-preview-collection", pageId, at, values, missing],
    queryFn: () => api.dryRunCollection(pageId!, { at, values, missing }),
    enabled: !!pageId && isCollectionId(pageId),
    retry: false,
  });
  const resolvedId = isCollectionId(pageId) ? collection.data?.page_id : pageId;
  const page = pages.find((entry) => entry.id === resolvedId);
  const detail = useQuery({
    queryKey: ["schedule-preview-page", resolvedId],
    queryFn: () => api.getPage(resolvedId!),
    enabled: !!resolvedId && !isCollectionId(resolvedId) && !page?.template,
    retry: false,
  });
  const resolved = page?.template ? page : detail.data;
  const preview = useQuery({
    queryKey: [
      "schedule-preview-at",
      boardId,
      at,
      resolvedId,
      values ?? null,
      missing ?? null,
      resolved?.revision,
      resolved?.template,
    ],
    queryFn: () => api.previewSchedulePage(resolved!, at, boardId, values, missing),
    enabled: !!resolvedId && !!resolved?.template,
    retry: false,
  });
  if (!pageId) return null;
  return (
    <>
      {preview.data && resolved && (
        <DevicePreview
          model={model}
          layers={preview.data.layers}
          ledLayout={target?.led_layout}
          message={preview.data.lines.join("\n")}
          size="sm"
          previewLabel={label}
        >
          <BoardViewport
            boardType={target?.board_color}
            code62Glyph={target?.code62_glyph}
            message={preview.data.lines.join("\n")}
            deviceType={resolved.device_type}
            notesWide={resolved.notes_wide}
            notesTall={resolved.notes_tall}
            gridRows={resolved.grid_rows ?? undefined}
            gridCols={resolved.grid_cols ?? undefined}
            layout="phone-hero"
            regionLabel={label}
          />
        </DevicePreview>
      )}
      {preview.isError && (
        <Text role="alert" tone="destructive">
          {preview.error.message}
        </Text>
      )}
    </>
  );
}
