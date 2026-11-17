import { Card, Stack, StaticBoardDisplay, Text } from "@fiestaboard/ui";

import { BoardViewport } from "@/components/board-viewport";
import { usePagePreview } from "@/hooks/use-board";
import { useLocale, useTranslations } from "@/i18n/translations";
import type { CollectionEvaluation, CollectionSelectionMode, Page } from "@/lib/api";

export interface CollectionPreviewProps {
  evaluation?: CollectionEvaluation;
  pages: Page[];
  mode: CollectionSelectionMode;
  dirty: boolean;
  loading: boolean;
  failed: boolean;
}

/** A saved-state evaluation, never physical board readback or a guess at a draft. */
export function CollectionPreview({ evaluation, pages, mode, dirty, loading, failed }: CollectionPreviewProps) {
  const t = useTranslations("collections");
  const tb = useTranslations("boardDisplay");
  const locale = useLocale();
  const selected = !dirty && !failed ? pages.find((p) => p.id === evaluation?.page_id) : undefined;
  const preview = usePagePreview(selected?.id ?? null);
  const geometry = selected
    ? {
        deviceType: selected.device_type,
        notesWide: selected.notes_wide ?? 1,
        notesTall: selected.notes_tall ?? 1,
        gridRows: selected.grid_rows ?? undefined,
        gridCols: selected.grid_cols ?? undefined,
      }
    : {};
  const time = evaluation?.at ? new Date(evaluation.at) : null;
  const formattedTime = time && Number.isFinite(time.getTime()) ? time.toLocaleString(locale) : "";
  return (
    <Card className="p-4 min-w-0">
      <Stack gap="3">
        <Text size="sm" weight="semibold">
          {t("nowInCollection")}
        </Text>
        {dirty ? (
          <Text size="sm" tone="muted">
            {t("previewSaveFirst")}
          </Text>
        ) : failed ? (
          <Text size="sm" tone="muted" role="status">
            {t("evaluationUnavailable")}
          </Text>
        ) : loading ? (
          <Text size="sm" tone="muted" role="status">
            {t("evaluationLoading")}
          </Text>
        ) : !selected ? (
          <Text size="sm" tone="muted">
            {t("evaluationEmpty")}
          </Text>
        ) : (
          <>
            {preview.isError ? (
              <Text size="sm" tone="muted">
                {t("evaluationUnavailable")}
              </Text>
            ) : mode === "random" ? (
              <BoardViewport
                {...geometry}
                message={preview.data?.message ?? null}
                isLoading={preview.isLoading}
                size="sm"
              />
            ) : (
              <StaticBoardDisplay
                {...geometry}
                message={preview.data?.message ?? null}
                size="sm"
                className="max-w-full"
                emptyLabel={tb("empty")}
                messageLabel={(message) => tb("withMessage", { message })}
              />
            )}
            <Text size="xs" weight="medium">
              {t("evaluatedPage", { name: selected.name })}
            </Text>
            {mode === "variable" && (
              <Text size="xs" tone="muted">
                {evaluation?.matched_rule == null
                  ? t("evaluationDefault")
                  : t("evaluationRule", { number: evaluation.matched_rule + 1 })}
              </Text>
            )}
            <Text size="xs" tone="muted">
              {t("savedEvaluation", { time: formattedTime })}
            </Text>
          </>
        )}
      </Stack>
    </Card>
  );
}
