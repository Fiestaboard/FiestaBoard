import { Skeleton, Text } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";

import { SettingsPanel } from "@/components/settings/settings-panel";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

/** Only label addresses we know; a container IP is not a shareable LAN URL. */
export function NetworkAddresses() {
  const t = useTranslations("settings.addresses");
  const { data, isPending } = useQuery({
    queryKey: ["debug-system-info"],
    queryFn: api.getDebugSystemInfo,
    retry: false,
    staleTime: 30_000,
  });
  return (
    <SettingsPanel title={t("title")} description={t("description")}>
      <dl className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-[minmax(0,1fr)_minmax(0,2fr)] sm:gap-4">
        <dt className="text-muted-foreground">{t("browser")}</dt>
        <dd className="break-all">{typeof window === "undefined" ? "—" : window.location.origin}</dd>
        <dt className="text-muted-foreground">{t("ip")}</dt>
        <dd className="font-mono break-all">
          {isPending ? <Skeleton className="h-4 w-32" /> : data?.server_ip || "—"}
        </dd>
      </dl>
      <Text size="xs" tone="muted" className="mt-3">
        {t("hint")}
      </Text>
    </SettingsPanel>
  );
}
