import { Card, Grid, ListRow, ListRowGroup, PageSection, Stack, Text } from "@fiestaboard/ui";

import { ScaledBoardDisplay } from "@/components/scaled-board-display";
import { useBoardCurrentMessage, useStatus } from "@/hooks/use-board";
import { useLocale, useTranslations } from "@/i18n/translations";
import type { BoardInstance } from "@/lib/api";
import { boardCharactersToTemplate } from "@/lib/board-characters-to-template";
import { isDisplayOffline } from "@/lib/status-banners";

/** H12 evidence from the hub; there is deliberately no manual-probe action. */
export function DisplayDiagnostics({ board }: { board: BoardInstance }) {
  const boardId = board.id;
  const { data: frame } = useBoardCurrentMessage(boardId, { poll: board.paused !== true });
  const comparable =
    (board.output ?? "vestaboard") === "vestaboard" &&
    frame?.api_mode === "local" &&
    frame.characters != null &&
    frame.expected_characters != null;
  const t = useTranslations("displays.fleet");
  const locale = useLocale();
  const { data } = useStatus();
  const health = data?.boards?.[boardId]?.health;
  const time = (iso: string | null | undefined) =>
    iso && !Number.isNaN(Date.parse(iso)) ? new Date(iso).toLocaleString(locale) : t("healthUnknown");
  return (
    <Grid gap="5" className="lg:grid-cols-[minmax(0,0.4fr)_minmax(0,1fr)]">
      <Card className="min-w-0 gap-4 p-5" data-testid="display-frame-comparison">
        <Text weight="medium">{t("preview")}</Text>
        {comparable ? (
          <Stack gap="4">
            {[
              { label: t("preview"), grid: frame.characters! },
              { label: t("expected"), grid: frame.expected_characters! },
            ].map(({ label, grid }, index) => (
              <Stack key={label} gap="2">
                {index > 0 && (
                  <Text size="sm" tone="muted">
                    {label}
                  </Text>
                )}
                <ScaledBoardDisplay
                  message={boardCharactersToTemplate(grid).join("\n")}
                  isStatic
                  size="sm"
                  boardType={board.board_color}
                  deviceType={board.device_type}
                  notesWide={board.notes_wide ?? 1}
                  notesTall={board.notes_tall ?? 1}
                  gridRows={board.grid_rows ?? undefined}
                  gridCols={board.grid_cols ?? undefined}
                  regionLabel={label}
                />
              </Stack>
            ))}
          </Stack>
        ) : (
          <Text size="sm" tone="muted">
            {t("readbackUnavailable")}
          </Text>
        )}
      </Card>
      <Card className="min-w-0 gap-0 py-0">
        <PageSection title={t("diagnostics")} data-testid="display-diagnostics">
          <ListRowGroup variant="plain">
            <ListRow
              title={t("connection")}
              meta={
                isDisplayOffline(health) ? t("unreachable") : health?.reachable === true ? t("online") : t("unknown")
              }
            />
            <ListRow title={t("lastConnectedLabel")} meta={time(health?.last_connected_at)} />
            <ListRow title={t("lastUpdateLabel")} meta={time(health?.last_update_at)} />
            <ListRow
              title={t("latency")}
              meta={health?.latency_ms != null ? `${health.latency_ms} ms` : t("unknown")}
            />
            <ListRow
              title={t("lastErrorLabel")}
              meta={health?.last_error ? t(`healthErrors.${health.last_error}`) : health ? t("no") : t("unknown")}
              description={health?.last_error_at ? time(health.last_error_at) : undefined}
            />
          </ListRowGroup>
        </PageSection>
      </Card>
    </Grid>
  );
}
