import { Box, Card, Flex, Stack, Text } from "@fiestaboard/ui";

import { BoardViewport } from "@/components/board-viewport";
import { formatDurationLabel } from "@/components/collection-schedule";
import { formatClock, formatSavedAt } from "@/components/ide/ide-format";
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
  /** Seconds each page shows (time) or between picks (random), for the Next line. */
  intervalSeconds?: number;
  /** "Weekdays 6:00 AM–9:00 AM" when the Schedule runs this Collection. */
  schedule?: string | null;
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
  intervalSeconds,
  schedule,
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
  const formattedTime = evaluation?.at ? formatSavedAt(evaluation.at, locale) : "";
  // Figma 312:74870: "Morning commute · showing until 7:15 AM" / "Next: Market open
  // (10 min) · Collection runs … in the Schedule", from the dry run's timeline. A
  // single window has no real end (it is the dry run's horizon), so it claims none.
  const timeline = mode !== "variable" ? (evaluation?.timeline ?? []) : [];
  const current = timeline.length > 1 && timeline[0].page_id === selected?.id ? timeline[0] : null;
  const nextPage = current ? pages.find((p) => p.id === timeline[1].page_id) : undefined;
  const nextLine = [
    nextPage && intervalSeconds
      ? t("nextPage", { name: nextPage.name, duration: formatDurationLabel(intervalSeconds, locale) })
      : null,
    schedule ? t("collectionRuns", { schedule }) : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Card role="region" aria-label={t(historical ? "testAtTime" : "nowInCollection")} className="p-4 md:p-3 min-w-0">
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
              className="min-w-0 md:w-[373px] md:max-w-full md:shrink-0"
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
                {current
                  ? t("showingUntil", { name: selected.name, time: formatClock(current.until, locale) })
                  : t("evaluatedPage", { name: selected.name })}
              </Text>
              {nextLine && (
                <Text size="xs" tone="muted">
                  {nextLine}
                </Text>
              )}
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
