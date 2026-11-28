"use client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Box,
  Skeleton,
} from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";

import { boardMeta } from "@/components/home/home-board";
import { InlineBoardPreview } from "@/components/inline-board-preview";
import { useTranslations } from "@/i18n/translations";
import { api, type CurrentDisplayResponse, type DeviceType } from "@/lib/api";
import { ApiError } from "@/lib/api/core";
import { resolveDimensions } from "@/lib/board-dimensions";

export interface ImportGeometry {
  deviceType: DeviceType;
  notesWide: number;
  notesTall: number;
  gridRows?: number | null;
  gridCols?: number | null;
}

function sizeKey(g: ImportGeometry): string {
  const dims = resolveDimensions(
    g.deviceType,
    g.notesWide,
    g.notesTall,
    g.gridRows ?? undefined,
    g.gridCols ?? undefined,
  );
  return `${g.deviceType}:${dims.cols}x${dims.rows}`;
}

/** As boardMeta reads it ("FiestaPanel TV 34 × 14"). */
function metaGeometry(g: ImportGeometry) {
  return { ...g, gridRows: g.gridRows ?? undefined, gridCols: g.gridCols ?? undefined };
}

function geometryOf(data: CurrentDisplayResponse): ImportGeometry {
  return {
    deviceType: data.device_type,
    notesWide: data.notes_wide,
    notesTall: data.notes_tall,
    gridRows: data.grid_rows,
    gridCols: data.grid_cols,
  };
}

/**
 * Import from board… (DD-W167, FABLE-2652 §5): a step, not a click. The dialog
 * shows what the page's board shows now, read-only, and asks before the
 * template is replaced. The replacement is the host's ordinary, undoable
 * edit; nothing here saves or shows anything. A board showing nothing, or a
 * page of another size (a template does not survive a geometry change), only
 * says so.
 */
export function ImportFromBoardDialog({
  open,
  onOpenChange,
  boardId,
  boardName,
  geometry,
  savedPage,
  onReplace,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The page's board; omitted, the hub's primary board. */
  boardId?: string;
  boardName: string;
  /** The page's geometry: an import never changes it. */
  geometry: ImportGeometry;
  /** A saved page reaches another size through Inspector › Shows on's copy row. */
  savedPage: boolean;
  onReplace: (data: CurrentDisplayResponse) => void;
}) {
  const t = useTranslations("importFromBoard");
  const tCommon = useTranslations("common");
  const query = useQuery({
    queryKey: ["current-display", boardId ?? null],
    queryFn: () => api.getCurrentDisplay(boardId),
    enabled: open,
    // What the board shows now, every time the dialog opens.
    staleTime: 0,
    gcTime: 0,
    retry: false,
  });
  const data = query.data;
  const showingNothing = query.error instanceof ApiError && query.error.status === 404;
  const otherSize = !!data && sizeKey(geometryOf(data)) !== sizeKey(geometry);
  const ready = !!data && !otherSize && !query.isFetching;

  let title: string;
  let body: string | null = null;
  if (query.isPending || (query.isFetching && !data)) {
    title = t("title", { board: boardName });
  } else if (showingNothing) {
    title = t("emptyTitle", { board: boardName });
    body = t("emptyBody");
  } else if (query.isError || !data) {
    title = t("errorTitle", { board: boardName });
    body = t("errorBody");
  } else if (otherSize) {
    title = t("sizeTitle", { board: boardName });
    body = [
      t("sizeBody", {
        page: data.page_name,
        theirs: boardMeta(undefined, metaGeometry(geometryOf(data))),
        ours: boardMeta(undefined, metaGeometry(geometry)),
      }),
      savedPage ? t("sizeCopyHint", { board: boardName }) : null,
    ]
      .filter(Boolean)
      .join(" ");
  } else {
    title = t("title", { board: boardName });
    body = t("showing", { board: boardName, page: data.page_name });
  }
  const askReplace = query.isPending || query.isFetching || ready;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent data-testid="import-from-board-dialog" className="sm:max-w-xl">
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          {body && <AlertDialogDescription>{body}</AlertDialogDescription>}
        </AlertDialogHeader>
        {askReplace && (
          // Boards keep their real tiles (owner rule 9): a tall one scrolls here, so
          // the buttons stay on screen.
          <Box
            data-slot="import-from-board-preview"
            aria-busy={!ready}
            className="max-h-[min(45dvh,24rem)] min-w-0 overflow-auto"
          >
            {ready && data ? (
              <InlineBoardPreview
                size="md"
                deviceType={data.device_type}
                regionLabel={t("previewLabel", { board: boardName })}
                snapshot={{
                  name: data.page_name,
                  board_id: boardId,
                  device_type: data.device_type,
                  notes_wide: data.notes_wide,
                  notes_tall: data.notes_tall,
                  grid_rows: data.grid_rows,
                  grid_cols: data.grid_cols,
                  template: data.template,
                  line_metadata: data.template.map((_, i) => ({
                    alignment: data.line_metadata?.[i]?.alignment ?? "left",
                    wrap: data.line_metadata?.[i]?.wrap ?? false,
                  })),
                }}
              />
            ) : (
              <Skeleton className="h-32 w-full rounded-md" />
            )}
          </Box>
        )}
        <AlertDialogFooter>
          {askReplace ? (
            <>
              <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
              <AlertDialogAction
                disabled={!ready}
                onClick={() => {
                  if (data && ready) onReplace(data);
                }}
              >
                {t("replace")}
              </AlertDialogAction>
            </>
          ) : (
            <AlertDialogCancel>{t("close")}</AlertDialogCancel>
          )}
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
