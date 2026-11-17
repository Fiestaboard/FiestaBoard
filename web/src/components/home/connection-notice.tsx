"use client";

import { StatusBanner, StatusBannerAction } from "@fiestaboard/ui";

import { useHubConnection } from "@/hooks/use-hub-connection";
import { useTranslations } from "@/i18n/translations";

/** Keeps an open send dialog and its content intact when the shared status poll loses the hub. */
export function HomeConnectionNotice() {
  const t = useTranslations("home.banners");
  const connection = useHubConnection();
  if (connection.deviceOnline && connection.hubReachable) return null;
  return (
    <StatusBanner
      kind={connection.deviceOnline ? "hub-unreachable" : "device-offline"}
      title={t(connection.deviceOnline ? "composeUnreachable" : "composeOffline")}
      description={t("composeDetail", { seconds: 15 })}
      action={<StatusBannerAction onClick={connection.retry}>{t("tryAgain")}</StatusBannerAction>}
    />
  );
}
