"use client";

import { StatusBanner, StatusBannerAction } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";

import { useCurrentBoard } from "@/components/current-board-context";
import { formatClock } from "@/components/home/home-status";
import Link from "@/components/smart-link";
import { queryKeys, usePages } from "@/hooks/use-board";
import { useLocale, useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

// 07a includes a 12 min warning. Jev all_modes_15min p=0.94: read the hub boundary for every silence mode.
const IMMINENT_THRESHOLD_SECONDS = 15 * 60;

export function SilenceImminentBanner() {
  const t = useTranslations("home.banners");
  const ts = useTranslations("statusBanners");
  const locale = useLocale();
  const { currentBoardId, currentBoard, boards } = useCurrentBoard();
  const scopedBoardId = boards.length > 1 && currentBoardId ? currentBoardId : undefined;
  const { data: status } = useQuery({
    queryKey: queryKeys.silenceStatus(scopedBoardId),
    queryFn: () => api.getSilenceStatus(scopedBoardId),
    refetchInterval: 30000,
  });
  const { data: pagesData } = usePages();
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(timer);
  }, []);
  const anchor = useMemo(
    () =>
      typeof status?.seconds_until_next_change === "number"
        ? { seconds: status.seconds_until_next_change, receivedAt: Date.now() }
        : null,
    [status],
  );
  void tick;
  if (!status?.enabled || status.active || !anchor) return null;
  const remaining = anchor.seconds - Math.floor((Date.now() - anchor.receivedAt) / 1000);
  if (remaining <= 0 || remaining > IMMINENT_THRESHOLD_SECONDS) return null;
  // Formatting the server's boundary is not a client-side Schedule prediction.
  const startsAt = new Date(anchor.receivedAt + anchor.seconds * 1000);
  const page = status.mode === "page" ? pagesData?.pages?.find((p) => p.id === status.page_id) : null;
  const board = currentBoard?.name ?? ts("unnamedBoard");
  const end = /^(\d{2}):(\d{2})/.exec(status.end_time_utc ?? "");
  const endTime =
    end && Number(end[1]) < 24 && Number(end[2]) < 60
      ? formatClock(new Date(Date.UTC(2000, 0, 1, Number(end[1]), Number(end[2]))), locale)
      : null;
  return (
    <StatusBanner
      kind="silence-soon"
      data-testid="silence-imminent-banner"
      title={t("silenceSoonTitle", { time: formatClock(startsAt, locale) })}
      description={
        page
          ? t(endTime ? "silenceSoonPageUntil" : "silenceSoonPage", {
              board,
              minutes: Math.ceil(remaining / 60),
              page: page.name,
              time: endTime ?? "",
            })
          : t(endTime ? "silenceSoonOtherUntil" : "silenceSoonOther", {
              board,
              minutes: Math.ceil(remaining / 60),
              time: endTime ?? "",
            })
      }
      action={
        <StatusBannerAction variant="ghost" asChild>
          <Link
            href={
              currentBoardId
                ? `/displays/${encodeURIComponent(currentBoardId)}?section=playback#silence-schedule`
                : "/schedule"
            }
          >
            {t("editSilence")}
          </Link>
        </StatusBannerAction>
      }
    />
  );
}
