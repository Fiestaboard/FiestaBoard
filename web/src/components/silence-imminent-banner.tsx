"use client";

import { StatusBanner, StatusBannerAction } from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { useCurrentBoard } from "@/components/current-board-context";
import { queryKeys, useActivePage, usePages } from "@/hooks/use-board";
import { useTranslations } from "@/i18n/translations";
import type { ActiveScheduleResponse, SilenceStatus } from "@/lib/api";
import { api } from "@/lib/api";

// Show the banner when silence is imminent within this many seconds.
const IMMINENT_THRESHOLD_SECONDS = 2 * 60;

export function SilenceImminentBanner() {
  const t = useTranslations("home");
  const queryClient = useQueryClient();

  // Track which upcoming boundary the user dismissed, so dismiss applies only
  // to the current "about to start" window and re-appears for tomorrow.
  const [dismissedFor, setDismissedFor] = useState<string | null>(null);

  // Local 1s ticker so the countdown decrements between server polls.
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  // Silence windows are per board (issue #1788). Scope only in multi-board
  // installs so single-board behavior is completely unchanged.
  const { currentBoardId, boards } = useCurrentBoard();
  const scopedBoardId = boards.length > 1 && currentBoardId ? currentBoardId : undefined;

  const { data: silenceStatus } = useQuery<SilenceStatus>({
    queryKey: queryKeys.silenceStatus(scopedBoardId),
    queryFn: () => api.getSilenceStatus(scopedBoardId),
    refetchInterval: 30_000,
  });

  const { data: pagesData } = usePages();

  // Reuse the queries ActivePageDisplay already populates so we don't double-fetch.
  const { data: activeScheduleData } = useQuery<ActiveScheduleResponse>({
    queryKey: ["schedules", "active"],
    queryFn: () => api.getActiveSchedule(),
    refetchInterval: 60_000,
  });
  const { data: manualActivePage } = useActivePage();
  const scheduleEnabled = activeScheduleData?.schedule_enabled ?? false;
  const activePageId = scheduleEnabled ? (activeScheduleData?.page_id ?? null) : (manualActivePage?.page_id ?? null);

  const switchNowMutation = useMutation({
    mutationFn: (vars: { pageId: string; durationMinutes: number }) =>
      api.setTemporaryOverride({
        page_id: vars.pageId,
        duration_minutes: vars.durationMinutes,
        revert_mode: "schedule",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["schedules", "active"] });
      queryClient.invalidateQueries({ queryKey: ["board-current-message"] });
      api.forceRefresh().catch(() => {});
      toast.success(t("silenceImminentSwitchSuccess"));
    },
    onError: () => {
      toast.error(t("silenceImminentSwitchFailed"));
    },
  });

  // Compute remaining seconds locally, anchored to the server's reading at
  // fetch time. This keeps the countdown smooth without spamming /silence-status.
  // useMemo (rather than useEffect+setState) keeps the anchor in sync with the
  // server snapshot without a cascading re-render.
  const anchor = useMemo<{ seconds: number; receivedAt: number } | null>(() => {
    const s = silenceStatus?.seconds_until_next_change;
    if (typeof s !== "number") return null;
    return { seconds: s, receivedAt: Date.now() };
  }, [silenceStatus]);

  if (!silenceStatus?.enabled) return null;
  if (silenceStatus.active) return null;
  if (silenceStatus.mode !== "page") return null;
  const silencePageId = silenceStatus.page_id;
  if (!silencePageId) return null;
  if (activePageId === silencePageId) return null;

  if (!anchor) return null;
  const elapsed = Math.floor((Date.now() - anchor.receivedAt) / 1000);
  const remaining = anchor.seconds - elapsed;
  void tick; // keep dependency on the local ticker

  if (remaining <= 0) return null;
  if (remaining > IMMINENT_THRESHOLD_SECONDS) return null;

  const boundaryKey = silenceStatus.next_change_utc;
  if (dismissedFor === boundaryKey) return null;

  const silencePage = pagesData?.pages?.find((p) => p.id === silencePageId) ?? null;
  const minutes = Math.max(0, Math.ceil(remaining / 60));

  const handleSwitchNow = () => {
    // Override duration must be ≥1 minute and long enough to bridge the gap
    // until silence naturally starts. Once silence starts, the regular silence
    // flow takes over (overriding the override) — so we don't need exact
    // duration math, just enough to span the wait.
    const durationMinutes = Math.max(1, Math.ceil(remaining / 60) + 1);
    switchNowMutation.mutate({ pageId: silencePageId, durationMinutes });
  };

  // A `StatusBanner kind="silence-soon"` (07a `298:2280`). Its two actions
  // stay: the ghost one dismisses this window only, the outline one switches
  // to the silence page now.
  return (
    <StatusBanner
      kind="silence-soon"
      data-testid="silence-imminent-banner"
      title={t("silenceImminentTitle", { minutes })}
      description={
        silencePage
          ? t("silenceImminentDescription", { pageName: silencePage.name })
          : t("silenceImminentDescriptionUnnamed")
      }
      action={
        <>
          <StatusBannerAction
            variant="ghost"
            onClick={() => setDismissedFor(boundaryKey)}
            disabled={switchNowMutation.isPending}
          >
            {t("silenceImminentDismiss")}
          </StatusBannerAction>
          <StatusBannerAction onClick={handleSwitchNow} disabled={switchNowMutation.isPending}>
            {t("silenceImminentSwitchNow")}
          </StatusBannerAction>
        </>
      }
    />
  );
}
