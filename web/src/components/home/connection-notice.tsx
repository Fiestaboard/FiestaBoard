"use client";

import { StatusBanner, StatusBannerAction } from "@fiestaboard/ui";

import { useHubConnection } from "@/hooks/use-hub-connection";
import { useLocale, useTranslations } from "@/i18n/translations";
import { browserHostname } from "@/lib/network-hint";

import { formatClock } from "./home-status";

/** Keeps an open send dialog and its content intact when the shared status poll loses the hub. */
export function HomeConnectionNotice({ composing = false }: { composing?: boolean }) {
  const t = useTranslations("home.banners");
  const connection = useHubConnection();
  const locale = useLocale();
  const time = connection.lastContactAt ? formatClock(new Date(connection.lastContactAt), locale) : null;
  if (connection.deviceOnline && connection.hubReachable) return null;
  return (
    <StatusBanner
      kind={connection.deviceOnline ? "hub-unreachable" : "device-offline"}
      title={t(connection.deviceOnline ? "composeUnreachable" : "composeOffline", { host: browserHostname() })}
      description={t(
        composing ? (time ? "composeDetailLast" : "composeDetail") : time ? "changeDetailLast" : "changeDetail",
        { seconds: 15, time: time ?? "" },
      )}
      action={<StatusBannerAction onClick={connection.retry}>{t("tryAgain")}</StatusBannerAction>}
    />
  );
}
