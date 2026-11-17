import { Button, Text } from "@fiestaboard/ui";

import { useOptionalGlobalAiPanel } from "@/components/global-ai-panel-context";
import { SettingsPanel } from "@/components/settings/settings-panel";
import { useTranslations } from "@/i18n/translations";

export function FiestaBotSettings() {
  const t = useTranslations("settings.fiestabot");
  const drawer = useOptionalGlobalAiPanel();
  return (
    <SettingsPanel title={t("title")} contentClassName="space-y-3">
      <Text size="sm">{t("scope")}</Text>
      <Text size="sm" tone="muted">
        {t("unavailable")}
      </Text>
      {drawer && (
        <Button variant="outline" onClick={drawer.open}>
          {t("open")}
        </Button>
      )}
    </SettingsPanel>
  );
}
