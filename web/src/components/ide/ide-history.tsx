"use client";

import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  Flex,
  ListRowGroup,
  RevisionDiff,
  RevisionRow,
  Skeleton,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { useTranslations } from "@/i18n/translations";
import { ApiError } from "@/lib/api";
import { type PageContent, pageHistoryApi, type PageRevisionSummary } from "@/lib/api/page-history";
import { useFormatEditTime } from "@/lib/edit-time";
import { changedRows, changeRegions } from "@/lib/ide/revision-diff";

import { type CreatorIdeState, ideKeys } from "./use-creator-ide";

/** A version's OVERVIEW: its content rendered with cached data at the open display. */
export function IdeThumbnail({ content, boardId }: { content: PageContent | undefined; boardId?: string }) {
  const rendered = useQuery({
    queryKey: ["ide", "thumbnail", boardId, JSON.stringify(content ?? null)],
    queryFn: () =>
      pageHistoryApi.renderAtBoard({
        template: content?.template ?? [],
        line_metadata: content?.line_metadata,
        device_type: content?.device_type,
        notes_wide: content?.notes_wide,
        notes_tall: content?.notes_tall,
        grid_rows: content?.grid_rows,
        grid_cols: content?.grid_cols,
        ...(boardId && { board_id: boardId }),
      }),
    enabled: !!content,
    staleTime: Infinity,
    retry: false,
  });
  if (!content || !rendered.data) return <Skeleton className="h-full w-full" aria-hidden="true" />;
  return (
    <ScaledBoardDisplay
      thumbnail
      isStatic
      size="sm"
      message={rendered.data.lines.join("\n")}
      deviceType={content.device_type ?? "flagship"}
      notesWide={content.notes_wide}
      notesTall={content.notes_tall}
      gridRows={content.grid_rows ?? undefined}
      gridCols={content.grid_cols ?? undefined}
    />
  );
}

function useRevisionContent(pageId: string, id: string | null) {
  return useQuery({
    queryKey: ideKeys.revision(pageId, id ?? ""),
    queryFn: () => pageHistoryApi.getRevision(pageId, id!),
    enabled: !!id,
    staleTime: Infinity,
    retry: false,
  });
}

function RevisionThumbnail({ pageId, id, boardId }: { pageId: string; id: string; boardId?: string }) {
  const detail = useRevisionContent(pageId, id);
  return <IdeThumbnail content={detail.data?.content} boardId={boardId} />;
}

/**
 * History (04d 1.8, H9a): the draft, saved versions newest first, Compare
 * against the draft (or the live page), and Restore, which always writes a
 * new draft and never touches what a display shows.
 */
export function IdeHistory({ ide, pageId }: { ide: CreatorIdeState; pageId: string }) {
  const t = useTranslations("creatorIde");
  const editTime = useFormatEditTime();
  const queryClient = useQueryClient();
  const [compareId, setCompareId] = useState<string | null>(null);
  const [confirmReplace, setConfirmReplace] = useState<string | null>(null);
  const live = ide.revisions.find((revision) => revision.current);
  const liveDetail = useRevisionContent(pageId, live?.id ?? null);
  const compared = useRevisionContent(pageId, compareId);
  const boardId = ide.pageBoardId ?? undefined;
  const boardName = ide.pageBoard?.name ?? t("aDisplay");

  const restore = useMutation({
    mutationFn: ({ id, replace }: { id: string; replace: boolean }) =>
      pageHistoryApi.restoreRevision(pageId, id, replace),
    onSuccess: (draft) => {
      queryClient.setQueryData(ideKeys.draft(pageId), draft);
      ide.invalidateHistory();
      setConfirmReplace(null);
      toast.success(t("restoredToDraft"), { description: t("restoredToDraftDetail", { board: boardName }) });
    },
    onError: (error, { id }) => {
      // Never retry a 409 with replace_draft on our own: the reader decides.
      if (error instanceof ApiError && error.status === 409) setConfirmReplace(id);
      else toast.error(t("restoreFailed"));
    },
  });
  const onRestore = (id: string) => restore.mutate({ id, replace: false });

  const author = (revision: PageRevisionSummary) =>
    revision.origin === "assistant" ? t("viaFiestaBot") : revision.via ? t(`via.${revision.via}`) : t("via.unknown");
  const summary = (revision: PageRevisionSummary) => {
    if (revision.restored_from) {
      const from = ide.revisions.find((other) => other.id === revision.restored_from);
      return t("restoredFrom", { time: from ? editTime(from.saved_at) : t("anEarlierVersion") });
    }
    return t(`origin.${revision.origin}`);
  };

  const labels = {
    overview: t("overview"),
    draft: t("stateDraft"),
    live: t("stateLive"),
    compare: t("compare"),
    restore: t("restore"),
    restoring: t("restoring"),
    restoreDescription: t("restoreDescription"),
  };

  // Compare: the chosen version against the draft when there is one, else the live page.
  const afterContent = ide.draft?.content ?? liveDetail.data?.content;
  const comparedRevision = ide.revisions.find((revision) => revision.id === compareId);
  const changes =
    compared.data && afterContent ? changedRows(compared.data.content.template ?? [], afterContent.template ?? []) : [];
  const rows = afterContent?.template?.length ?? 0;
  const diffSummary =
    changes.length === 1
      ? t("oneRowChanged", {
          row: changes[0].row + 1,
          before: changes[0].before.trim(),
          after: changes[0].after.trim(),
        })
      : t("rowsChanged", { count: changes.length });

  if (ide.revisionsError) {
    return (
      <Text size="sm" tone="muted">
        {t("historyUnavailable")}
      </Text>
    );
  }

  return (
    <Stack gap="3" data-slot="ide-history">
      {ide.draft && (
        <Stack gap="2" data-slot="ide-draft">
          <Text size="sm" weight="medium">
            {ide.draft.stale
              ? t("draftStale", { time: editTime(ide.draft.saved_at) })
              : t("draftSaved", { time: editTime(ide.draft.saved_at), board: boardName })}
          </Text>
          <Flex gap="2" className="flex-wrap">
            <Button
              variant="secondary"
              disabled={ide.publishDraft.isPending || ide.builder.unsaved}
              onClick={() => ide.publishDraft.mutate()}
            >
              {t("publishDraft")}
            </Button>
            <Button variant="outline" disabled={ide.discardDraft.isPending} onClick={() => ide.discardDraft.mutate()}>
              {t("discardDraft")}
            </Button>
          </Flex>
          {ide.builder.unsaved && (
            <Text size="xs" tone="muted">
              {t("publishNeedsSavedEdits")}
            </Text>
          )}
        </Stack>
      )}
      {compareId && comparedRevision && (
        <RevisionDiff
          data-slot="ide-revision-diff"
          before={{
            label: editTime(comparedRevision.saved_at),
            status: comparedRevision.current ? "live" : undefined,
            thumbnail: <IdeThumbnail content={compared.data?.content} boardId={boardId} />,
          }}
          after={{
            label: ide.draft ? t("now") : editTime(live?.saved_at ?? ""),
            status: ide.draft ? "draft" : "live",
            thumbnail: <IdeThumbnail content={afterContent} boardId={boardId} />,
          }}
          changes={changeRegions(changes, rows)}
          summary={compared.data ? diffSummary : undefined}
          loading={restore.isPending}
          onRestore={comparedRevision.current ? undefined : () => onRestore(comparedRevision.id)}
          labels={{
            ...labels,
            comparison: t("comparison"),
            changedRegions: (count) => t("rowsChanged", { count }),
          }}
        />
      )}
      {ide.revisions.length ? (
        <ListRowGroup variant="plain" aria-label={t("versions", { count: ide.revisions.length })}>
          {ide.revisions.map((revision) => (
            <RevisionRow
              key={revision.id}
              thumbnail={<RevisionThumbnail pageId={pageId} id={revision.id} boardId={boardId} />}
              savedAt={editTime(revision.saved_at)}
              dateTime={revision.saved_at}
              author={author(revision)}
              summary={summary(revision)}
              current={revision.id === compareId}
              status={revision.current ? "live" : undefined}
              onCompare={() => setCompareId(revision.id === compareId ? null : revision.id)}
              onRestore={revision.current ? undefined : () => onRestore(revision.id)}
              loading={restore.isPending && restore.variables?.id === revision.id}
              labels={labels}
            />
          ))}
        </ListRowGroup>
      ) : (
        <Text size="sm" tone="muted">
          {t("noVersions")}
        </Text>
      )}
      <AlertDialog open={!!confirmReplace} onOpenChange={(open) => !open && setConfirmReplace(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("replaceDraftTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("replaceDraftDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("keepDraft")}</AlertDialogCancel>
            <Button
              variant="destructive"
              disabled={restore.isPending}
              onClick={() => confirmReplace && restore.mutate({ id: confirmReplace, replace: true })}
            >
              {t("replaceDraft")}
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Stack>
  );
}
