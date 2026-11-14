"use client";

import { Stack, StatusBanner, StatusBannerAction, Text } from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { toast } from "sonner";

import { BoardInitErrorBanner } from "@/components/board-init-error-banner";
import { useCurrentBoard } from "@/components/current-board-context";
import { isVirtualBoard } from "@/components/settings/output-boards";
import { SilenceImminentBanner } from "@/components/silence-imminent-banner";
import Link from "@/components/smart-link";
import { queryKeys, STATUS_POLL_MS, usePages, useStatus } from "@/hooks/use-board";
import { useHubConnection } from "@/hooks/use-hub-connection";
import { PANELS_QUERY_KEY } from "@/hooks/use-panel-targets";
import { useLocale, useTranslations } from "@/i18n/translations";
import { api, sessionsApi, type SilenceStatus } from "@/lib/api";
import { browserHostname } from "@/lib/network-hint";
import { formatRelativeTime } from "@/lib/relative-time";
import { silenceEndsAt } from "@/lib/silence-until";
import {
  panelViewer,
  type PickedStatusBanner,
  type PickedStatusBannerKind,
  pickStatusBanner,
  type StatusBannerBoard,
} from "@/lib/status-banners";
import { cn } from "@/lib/utils";

/** Where the hub-unreachable banner's "Connection help" goes. */
export const CONNECTION_HELP_URL = "https://fiestaboard.app/docs/troubleshooting#web-ui-issues";

const SESSIONS_QUERY_KEY = ["auth-sessions", "viewers"] as const;

export interface StatusBannerHostProps {
  /** The board the banner is about; omitted means the board the user is managing. */
  boardId?: string;
  /**
   * Kinds this page already says some other way. The next kind down still
   * shows. Home passes `silenced` while its Now-showing card carries the
   * Silence notice (slice 2.2 moves that here).
   */
  exclude?: ReadonlyArray<PickedStatusBannerKind>;
  /** Also render the fleet-wide init-error banners and the silence-soon banner (Home). */
  fleet?: boolean;
  className?: string;
}

function timeLabel(at: Date | number | string | null | undefined): string | null {
  if (at == null) return null;
  const date = at instanceof Date ? at : new Date(at);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

/** Whether this looks like a phone, for "This phone / This computer has no network". */
function isPhone(): boolean {
  return typeof window !== "undefined" && (window.matchMedia?.("(pointer: coarse)").matches ?? false);
}

/**
 * The page's one persistent status banner (WEB-10; 07a `Web / Banner`
 * `298:2280`), under the PageHeader: you're offline, can't reach the hub, a
 * display offline (H12), paused, silenced, no TV viewer (H13b). Each kind
 * has its one fix. Which kind wins is `pickStatusBanner`'s order.
 *
 * Reads the shared status poll, the board settings, the silence status and,
 * for a FiestaPanel only, the panel and signed-in-TV lists; adds no polling
 * loop beyond those queries.
 */
export function StatusBannerHost({ boardId, exclude = [], fleet = false, className }: StatusBannerHostProps) {
  const t = useTranslations("statusBanners");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const queryClient = useQueryClient();
  const connection = useHubConnection();
  const { data: status } = useStatus();
  const { data: pagesData } = usePages();
  const { boards, currentBoardId } = useCurrentBoard();

  const targetId = boardId ?? currentBoardId;
  const instance = boards.find((b) => b.id === targetId);
  const boardStatus = targetId ? status?.boards?.[targetId] : undefined;
  // Silence windows are per board (#1788); a single-board install asks unscoped, as before.
  const silenceBoardId = boardId ?? (boards.length > 1 && currentBoardId ? currentBoardId : undefined);

  const { data: silenceStatus } = useQuery<SilenceStatus>({
    queryKey: queryKeys.silenceStatus(silenceBoardId),
    queryFn: () => api.getSilenceStatus(silenceBoardId),
    refetchInterval: 30_000,
    enabled: Boolean(targetId),
  });

  // FiestaPanel only: is any signed-in TV showing it (H13b)?
  const isPanelBoard = instance ? isVirtualBoard(instance) : false;
  const { data: panelsData } = useQuery({
    queryKey: PANELS_QUERY_KEY,
    queryFn: () => api.listPanels(),
    staleTime: 60_000,
    enabled: isPanelBoard,
  });
  const panel = panelsData?.panels?.find((p) => p.board_id === targetId);
  // The HDMI display panel is shown by the FiestaPi itself, never by a signed-in TV.
  const watchViewers = Boolean(panel && !panel.is_display);
  const { data: sessionsData, refetch: refetchSessions } = useQuery({
    queryKey: SESSIONS_QUERY_KEY,
    queryFn: () => sessionsApi.listSessions(),
    enabled: watchViewers,
    // Sign-in off answers 401: the viewers are not known here, so no banner.
    retry: false,
    refetchInterval: 60_000,
  });

  const pageName = (id: string | null | undefined) => (id && pagesData?.pages?.find((p) => p.id === id)?.name) || null;

  const board: StatusBannerBoard | null = targetId
    ? {
        id: targetId,
        name: instance?.name ?? "",
        paused: instance?.paused ?? boardStatus?.paused ?? false,
        error: boardStatus?.error ?? null,
        health: boardStatus?.health ?? null,
        viewer:
          watchViewers && panel && sessionsData ? panelViewer(panel.id, sessionsData.sessions, Date.now()) : undefined,
      }
    : null;

  const silenceUntil = silenceEndsAt(silenceStatus);
  const banner = pickStatusBanner(
    {
      deviceOnline: connection.deviceOnline,
      hubReachable: connection.hubReachable,
      lastHubContactAt: connection.lastContactAt,
      board,
      silence: silenceStatus?.active
        ? {
            active: true,
            until: silenceUntil ? silenceUntil.toISOString() : null,
            mode: silenceStatus.mode,
            pageName: pageName(silenceStatus.page_id),
          }
        : null,
    },
    exclude,
  );

  const resume = useMutation({
    mutationFn: (id: string) => api.setBoardPaused(id, false),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
      queryClient.invalidateQueries({ queryKey: queryKeys.status });
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const online = connection.deviceOnline && connection.hubReachable;

  return (
    <Stack gap="2" className={cn("empty:hidden", className)} data-testid="status-banners">
      {banner ? (
        <Banner
          picked={banner}
          t={t}
          opensInNewTab={tCommon("opensInNewTab")}
          locale={locale}
          activePageName={pageName(boardStatus?.active_page_id)}
          onRetry={connection.retry}
          onResume={(id) => resume.mutate(id)}
          resuming={resume.isPending}
          onCheckViewers={() => void refetchSessions()}
        />
      ) : null}
      {/* Fleet-wide (#1829): every board that failed to start, not only this one. */}
      {fleet && online ? <BoardInitErrorBanner /> : null}
      {fleet && online && !banner ? <SilenceImminentBanner /> : null}
    </Stack>
  );
}

type Translate = ReturnType<typeof useTranslations>;

function Banner({
  picked,
  t,
  opensInNewTab,
  locale,
  activePageName,
  onRetry,
  onResume,
  resuming,
  onCheckViewers,
}: {
  picked: PickedStatusBanner;
  t: Translate;
  opensInNewTab: string;
  locale: string;
  activePageName: string | null;
  onRetry: () => void;
  onResume: (boardId: string) => void;
  resuming: boolean;
  onCheckViewers: () => void;
}) {
  // `key={kind}`: a new kind is a new banner, so its live region announces it
  // with its own urgency instead of swapping a role in place.
  switch (picked.kind) {
    case "device-offline":
      return (
        <StatusBanner
          key={picked.kind}
          kind="device-offline"
          title={t("deviceOfflineTitle")}
          description={isPhone() ? t("deviceOfflinePhone") : t("deviceOfflineComputer")}
          action={<StatusBannerAction onClick={onRetry}>{t("tryAgain")}</StatusBannerAction>}
        />
      );
    case "hub-unreachable": {
      const time = timeLabel(picked.lastContactAt);
      const seconds = Math.round(STATUS_POLL_MS / 1000);
      return (
        <StatusBanner
          key={picked.kind}
          kind="hub-unreachable"
          title={t("hubUnreachableTitle", { host: browserHostname() })}
          description={
            time ? t("hubUnreachableDetail", { time, seconds }) : t("hubUnreachableDetailNever", { seconds })
          }
          action={
            <>
              <StatusBannerAction onClick={onRetry}>{t("tryAgain")}</StatusBannerAction>
              <StatusBannerAction variant="ghost" asChild>
                {/* eslint-disable-next-line react/forbid-elements -- single Slot child of StatusBannerAction asChild; the Button merges its chrome onto this anchor and TextLink would layer conflicting link styling (as system-update.tsx) */}
                <a href={CONNECTION_HELP_URL} target="_blank" rel="noopener noreferrer">
                  {t("connectionHelp")}
                  <ExternalLink aria-hidden="true" />
                  <Text as="span" className="sr-only">
                    {opensInNewTab}
                  </Text>
                </a>
              </StatusBannerAction>
            </>
          }
        />
      );
    }
    case "display-offline": {
      const time = timeLabel(picked.lastConnectedAt);
      const name = picked.board.name || t("unnamedBoard");
      return (
        <StatusBanner
          key={picked.kind}
          kind="display-offline"
          title={t("displayOfflineTitle", { boardName: name })}
          description={time ? t("displayOfflineDetail", { time }) : t("displayOfflineDetailNever")}
          action={
            <StatusBannerAction asChild>
              <Link href={`/displays/${encodeURIComponent(picked.board.id)}?section=settings`}>{t("diagnostics")}</Link>
            </StatusBannerAction>
          }
        />
      );
    }
    case "paused": {
      const name = picked.board.name || t("unnamedBoard");
      return (
        <StatusBanner
          key={picked.kind}
          kind="paused"
          title={t("pausedTitle", { boardName: name })}
          description={activePageName ? t("pausedDetail", { pageName: activePageName }) : t("pausedDetailNoPage")}
          action={
            <StatusBannerAction onClick={() => onResume(picked.board.id)} disabled={resuming}>
              {t("resume")}
            </StatusBannerAction>
          }
        />
      );
    }
    case "silenced": {
      const name = picked.board.name || t("unnamedBoard");
      const time = timeLabel(picked.silence.until);
      const page = picked.silence.mode === "page" ? picked.silence.pageName : null;
      return (
        <StatusBanner
          key={picked.kind}
          kind="silenced"
          title={time ? t("silencedTitle", { time }) : t("silencedTitleNoTime")}
          description={
            page && time
              ? t("silencedDetailPage", { boardName: name, pageName: page, time })
              : time
                ? t("silencedDetail", { boardName: name, time })
                : t("silencedDetailNoTime", { boardName: name })
          }
        />
      );
    }
    case "no-viewer": {
      const name = picked.board.name || t("unnamedBoard");
      return (
        <StatusBanner
          key={picked.kind}
          kind="no-viewer"
          title={t("noViewerTitle", { boardName: name })}
          description={
            picked.lastShown
              ? t("noViewerDetail", {
                  deviceName: picked.lastShown.deviceName,
                  when: formatRelativeTime(picked.lastShown.at, locale),
                })
              : t("noViewerDetailNever")
          }
          action={<StatusBannerAction onClick={onCheckViewers}>{t("checkAgain")}</StatusBannerAction>}
        />
      );
    }
  }
}
