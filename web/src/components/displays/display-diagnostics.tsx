import { ListRow, ListRowGroup, PageSection } from "@fiestaboard/ui";

import { useStatus } from "@/hooks/use-board";
import { useLocale, useTranslations } from "@/i18n/translations";
import { isDisplayOffline } from "@/lib/status-banners";

/** H12 evidence from the hub; there is deliberately no manual-probe action. */
export function DisplayDiagnostics({ boardId }: { boardId: string }) {
  const t = useTranslations("displays.fleet");
  const locale = useLocale();
  const { data } = useStatus();
  const health = data?.boards?.[boardId]?.health;
  const time = (iso: string | null | undefined) =>
    iso && !Number.isNaN(Date.parse(iso)) ? new Date(iso).toLocaleString(locale) : t("healthUnknown");
  return (
    <PageSection title={t("diagnostics")} data-testid="display-diagnostics">
      <ListRowGroup variant="plain">
        <ListRow
          title={t("connection")}
          meta={isDisplayOffline(health) ? t("unreachable") : health?.reachable === true ? t("online") : t("unknown")}
        />
        <ListRow title={t("lastConnectedLabel")} meta={time(health?.last_connected_at)} />
        <ListRow title={t("lastUpdateLabel")} meta={time(health?.last_update_at)} />
        <ListRow title={t("latency")} meta={health?.latency_ms != null ? `${health.latency_ms} ms` : t("unknown")} />
        <ListRow
          title={t("lastErrorLabel")}
          meta={health?.last_error ? t(`healthErrors.${health.last_error}`) : health ? t("no") : t("unknown")}
          description={health?.last_error_at ? time(health.last_error_at) : undefined}
        />
      </ListRowGroup>
    </PageSection>
  );
}
