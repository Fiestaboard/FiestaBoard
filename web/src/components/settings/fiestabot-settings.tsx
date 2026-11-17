import { Button, Skeleton, Stack, Text } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";

import { useOptionalGlobalAiPanel } from "@/components/global-ai-panel-context";
import { SettingsPanel } from "@/components/settings/settings-panel";
import Link from "@/components/smart-link";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

export function FiestaBotSettings() {
  const t = useTranslations("settings.fiestabot");
  const drawer = useOptionalGlobalAiPanel();
  // Share the drawer's settings cache. It closes when AI is disabled and
  // renders nothing without providers; a context alone cannot make it usable.
  const readiness = useQuery({
    queryKey: ["ai-settings"],
    queryFn: api.getAiSettings,
    retry: false,
  });
  const ready = readiness.data?.enabled && (readiness.data.providers?.length ?? 0) > 0;
  const setup = (
    <Button variant="outline" asChild>
      <Link href="/settings/ai-provider">{t("setup")}</Link>
    </Button>
  );

  return (
    <SettingsPanel title={t("title")} contentClassName="space-y-3">
      <Text size="sm">{t("scope")}</Text>
      <Text size="sm" tone="muted">
        {t("unavailable")}
      </Text>
      {readiness.isPending ? (
        <Stack gap="2">
          <Text role="status" size="sm">
            {t("checking")}
          </Text>
          <Skeleton className="h-9 w-40" />
        </Stack>
      ) : readiness.isError ? (
        <Stack gap="3">
          <Text role="alert" size="sm">
            {t("checkFailed")}
          </Text>
          <Button variant="outline" disabled={readiness.isFetching} onClick={() => void readiness.refetch()}>
            {t("retry")}
          </Button>
          {setup}
        </Stack>
      ) : ready ? (
        drawer && (
          <Button variant="outline" onClick={drawer.open}>
            {t("open")}
          </Button>
        )
      ) : (
        <Stack gap="3">
          <Text size="sm" tone="muted">
            {t("needsSetup")}
          </Text>
          {setup}
        </Stack>
      )}
    </SettingsPanel>
  );
}
