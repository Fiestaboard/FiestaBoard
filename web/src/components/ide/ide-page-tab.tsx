"use client";

import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DurationChipGroup,
  InspectorRow,
  Label,
  List,
  ListItem,
  ListRow,
  ListRowGroup,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type RefObject, useState } from "react";
import { Link } from "react-router";

import type { PageBuilderHandle } from "@/components/page-builder";
import { queryKeys } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";
import { type PageDuplicateResponse, pageHistoryApi } from "@/lib/api/page-history";
import { jumpToTemplateLine } from "@/lib/ide/jump-to-line";
import { templateReferences } from "@/lib/ide/references";

import type { CreatorIdeState } from "./use-creator-ide";

/** Page durations the hub accepts (10 s – 1 h), as drawn in 04d 1.6. */
export const DURATION_CHOICES = [10, 30, 60, 300, 900, 3600] as const;

/** The built-in transitions, keyed to the shared transitionSettings labels. */
export const TRANSITIONS: { value: string; labelKey: string }[] = [
  { value: "column", labelKey: "column" },
  { value: "reverse-column", labelKey: "reverseColumn" },
  { value: "edges-to-center", labelKey: "edgesToCenter" },
  { value: "row", labelKey: "row" },
  { value: "diagonal", labelKey: "diagonal" },
  { value: "random", labelKey: "random" },
];
const INHERIT = "__inherit__";

export function formatDuration(seconds: number, t: (key: string, params?: Record<string, unknown>) => string) {
  if (seconds >= 3600 && seconds % 3600 === 0) return t("hours", { count: seconds / 3600 });
  if (seconds >= 60 && seconds % 60 === 0) return t("minutes", { count: seconds / 60 });
  return t("seconds", { count: seconds });
}

/**
 * Page settings that live on the page rather than in the template. They are
 * written to the page itself, so they wait until the editor has nothing
 * unsaved (the editor would otherwise save over them with a stale revision).
 */
function PageSettingsDialog({
  field,
  onClose,
  ide,
  pageId,
  builderRef,
}: {
  field: "duration" | "transition" | null;
  onClose: () => void;
  ide: CreatorIdeState;
  pageId: string;
  builderRef: RefObject<PageBuilderHandle | null>;
}) {
  const t = useTranslations("creatorIde");
  const tTransitions = useTranslations("transitionSettings");
  const tBuilder = useTranslations("pageBuilder");
  const snapshot = ide.builder.snapshot;
  const [duration, setDuration] = useState<string>(String(snapshot?.duration_seconds ?? 300));
  const [transition, setTransition] = useState<string>(snapshot?.transition_strategy ?? INHERIT);
  const save = useMutation({
    mutationFn: () =>
      api.updatePage(pageId, {
        expected_revision: snapshot?.revision ?? undefined,
        ...(field === "duration"
          ? { duration_seconds: Number(duration) }
          : { transition_strategy: transition === INHERIT ? null : transition }),
      }),
    onSuccess: async () => {
      await builderRef.current?.reloadFromServer();
      ide.invalidateHistory();
      onClose();
    },
  });
  const blocked = ide.builder.unsaved;
  return (
    <Dialog open={!!field} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{field === "duration" ? t("pageDuration") : t("transition")}</DialogTitle>
          <DialogDescription>{blocked ? t("settingsNeedSavedEdits") : t("settingsSavedWithPage")}</DialogDescription>
        </DialogHeader>
        {field === "duration" ? (
          <DurationChipGroup
            aria-label={t("pageDuration")}
            layout="grid"
            value={duration}
            onValueChange={(value) => setDuration(String(value))}
            options={DURATION_CHOICES.map((seconds) => ({
              value: String(seconds),
              label: formatDuration(seconds, t),
              disabled: blocked,
            }))}
          />
        ) : (
          <Stack gap="2">
            <Label htmlFor="ide-transition">{t("transition")}</Label>
            <Select value={transition} onValueChange={(value) => setTransition(String(value))} disabled={blocked}>
              <SelectTrigger id="ide-transition">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={INHERIT}>{tBuilder("transitionUseDisplayTransition")}</SelectItem>
                {TRANSITIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {tTransitions(`strategies.${option.labelKey}.label`)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Stack>
        )}
        {save.isError && (
          <Text size="sm" tone="destructive" role="alert">
            {t("settingsFailed")}
          </Text>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t("cancel")}
          </Button>
          <Button disabled={blocked || save.isPending} onClick={() => save.mutate()}>
            {t("saveToPage")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * "Make a copy for another display…" (04d 1.6b, H9c): the copy is made at
 * the chosen display's size and opens with the hub's crop report.
 */
export function DuplicateDialog({
  open,
  onOpenChange,
  ide,
  pageId,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  ide: CreatorIdeState;
  pageId: string;
}) {
  const t = useTranslations("creatorIde");
  const queryClient = useQueryClient();
  const [result, setResult] = useState<PageDuplicateResponse | null>(null);
  const duplicate = useMutation({
    mutationFn: (boardId: string) => pageHistoryApi.duplicatePage(pageId, { board_id: boardId }),
    onSuccess: (response) => {
      setResult(response);
      void queryClient.invalidateQueries({ queryKey: queryKeys.pages });
    },
  });
  const close = (next: boolean) => {
    if (!next) {
      setResult(null);
      duplicate.reset();
    }
    onOpenChange(next);
  };
  const report = result?.report;
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{result ? t("copyMade", { name: result.page.name }) : t("makeCopy")}</DialogTitle>
          <DialogDescription>{result ? t("cropReport") : t("pickDisplay")}</DialogDescription>
        </DialogHeader>
        {report ? (
          <Stack gap="1" data-slot="ide-crop-report">
            <Text size="sm">
              {t("copySize", {
                cols: report.cols,
                rows: report.rows,
                fromCols: report.from_cols,
                fromRows: report.from_rows,
              })}
            </Text>
            {report.lines_too_long.length > 0 && (
              <Text size="sm">{t("cropTooLong", { count: report.lines_too_long.length })}</Text>
            )}
            {report.rows_dropped.length > 0 && (
              <Text size="sm">{t("cropRowsDropped", { count: report.rows_dropped.length })}</Text>
            )}
            {report.canvases_scaled > 0 && (
              <Text size="sm">{t("cropCanvases", { count: report.canvases_scaled })}</Text>
            )}
            {report.drawing?.source === "baseline" && <Text size="sm">{t("cropUnknownDrawing")}</Text>}
            {!report.lines_too_long.length && !report.rows_dropped.length && (
              <Text size="sm" tone="muted">
                {t("cropNothingLost")}
              </Text>
            )}
          </Stack>
        ) : ide.boards.length ? (
          <ListRowGroup>
            {ide.boards.map((board) => (
              <ListRow
                key={board.id}
                title={board.name}
                description={board.id === ide.currentBoardId ? t("thisDisplay") : undefined}
                render={<button type="button" disabled={duplicate.isPending} />}
                onClick={() => duplicate.mutate(board.id)}
              />
            ))}
          </ListRowGroup>
        ) : (
          <Text size="sm" tone="muted">
            {t("noDisplays")}
          </Text>
        )}
        {duplicate.isError && (
          <Text size="sm" tone="destructive" role="alert">
            {t("copyFailed")}
          </Text>
        )}
        <DialogFooter>
          {result ? (
            <>
              <Button variant="outline" onClick={() => close(false)}>
                {t("close")}
              </Button>
              <Button asChild onClick={() => close(false)}>
                <Link to={`/pages/edit/${encodeURIComponent(result.page.id)}`}>{t("openCopy")}</Link>
              </Button>
            </>
          ) : (
            <Button variant="outline" onClick={() => close(false)}>
              {t("cancel")}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** The Page tab (04d 4.3 Inspector, drawn): duration, transition, missing-data fallback, copy. */
export function IdePageTab({
  ide,
  pageId,
  builderRef,
  onMakeCopy,
}: {
  ide: CreatorIdeState;
  pageId: string;
  builderRef: RefObject<PageBuilderHandle | null>;
  onMakeCopy: () => void;
}) {
  const t = useTranslations("creatorIde");
  const tTransitions = useTranslations("transitionSettings");
  const [field, setField] = useState<"duration" | "transition" | null>(null);
  const snapshot = ide.builder.snapshot;
  const fallbacks = templateReferences(snapshot?.template ?? []).fallbacks;
  const boardName = ide.currentBoard?.name ?? t("aDisplay");
  const transitionKey = TRANSITIONS.find((option) => option.value === snapshot?.transition_strategy)?.labelKey;
  return (
    <>
      <List gap="0" role="list" data-slot="ide-page-tab">
        <ListItem>
          <InspectorRow
            title={t("pageDuration")}
            detail={t("pageDurationDetail")}
            value={formatDuration(snapshot?.duration_seconds ?? 300, t)}
            chevron
            onPress={() => setField("duration")}
          />
        </ListItem>
        <ListItem>
          <InspectorRow
            title={t("transition")}
            detail={
              snapshot?.transition_strategy
                ? t("transitionOverrides", { board: boardName })
                : t("transitionInherits", { board: boardName })
            }
            value={transitionKey ? tTransitions(`strategies.${transitionKey}.label`) : t("displayDefault")}
            chevron
            onPress={() => setField("transition")}
          />
        </ListItem>
        <ListItem>
          <InspectorRow
            title={t("whenMissing")}
            detail={fallbacks.length ? t("fallbackCount", { count: fallbacks.length }) : t("fallbackNone")}
            value={fallbacks.length ? t("fallbackText") : undefined}
            chevron={fallbacks.length > 0}
            disabled={!fallbacks.length}
            onPress={() => fallbacks[0] && jumpToTemplateLine(fallbacks[0].line)}
          />
        </ListItem>
        <ListItem>
          <InspectorRow title={t("makeCopy")} detail={t("makeCopyDetail")} chevron onPress={onMakeCopy} />
        </ListItem>
      </List>
      {field && (
        <PageSettingsDialog
          field={field}
          onClose={() => setField(null)}
          ide={ide}
          pageId={pageId}
          builderRef={builderRef}
        />
      )}
    </>
  );
}
