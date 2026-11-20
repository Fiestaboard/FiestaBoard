import { Box, Card, Flex, Stack, Text } from "@fiestaboard/ui";

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
  historical?: boolean;
}

/** A saved-state evaluation, never physical board readback or a guess at a draft. */
export function CollectionPreview({
  evaluation,
  pages,
  mode,
  dirty,
  loading,
  failed,
  historical = false,
}: CollectionPreviewProps) {
  const t = useTranslations("collections");
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
    <Card
      role="region"
      aria-label={t(historical ? "testAtTime" : "nowInCollection")}
      className="p-4 md:p-3 lg:p-4 min-w-0"
    >
      <Stack gap="3">
        <Text size="sm" weight="semibold" className="md:hidden lg:block">
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
          <Flex direction="col" gap="4" className="min-w-0 md:flex-row lg:flex-col">
            <Box
              data-testid="collection-preview-board"
              aria-busy={preview.isFetching}
              className="min-w-0 md:w-[373px] md:shrink-0 lg:w-auto"
            >
              {preview.isError ? (
                <Text size="sm" tone="muted">
                  {t("evaluationUnavailable")}
                </Text>
              ) : (
                // A viewport, not a fixed-size board centred in the card, which
                // was clipped on both sides at 390 (BB-B-12).
                <BoardViewport
                  {...geometry}
                  message={preview.data?.message ?? null}
                  isLoading={preview.isLoading}
                  layout="phone-hero"
                  // A glance at what the Collection shows: the whole board first
                  // (Actual size is a tap away), not its left 16 columns.
                  defaultMode="fit"
                  persist={false}
                  isStatic={mode !== "random"}
                />
              )}
            </Box>
            <Stack gap="2" className="min-w-0 md:flex-1 md:justify-center">
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
            </Stack>
          </Flex>
        )}
      </Stack>
    </Card>
  );
}
