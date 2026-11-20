"use client";

import {
  Alert,
  AlertDescription,
  Badge,
  type BoardCellGrid,
  Box,
  Button,
  Card,
  CardTitle,
  Countdown,
  Flex,
  Kbd,
  NowShowingCard,
  type NowShowingMode,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Calendar, ChevronRight, LayoutGrid, Pause, PencilLine, Radio } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { BoardOutOfSyncBanner } from "@/components/board-out-of-sync-banner";
import { useCurrentBoard } from "@/components/current-board-context";
import { type BoardActions, BoardActionsMenu, BoardContextMenu } from "@/components/home/board-context-menu";
import { ChangePageDialog } from "@/components/home/change-page-dialog";
import { boardMeta, HomeBoard } from "@/components/home/home-board";
import { formatClock, formatSpan, overrideOnScreen, scheduleNextChange } from "@/components/home/home-status";
import { HomeSupportingPane } from "@/components/home/home-supporting-pane";
import {
  nudgeDisplay,
  overrideUndoToastId,
  useActiveTrigger,
  useBoardDetail,
  useRefreshHomeStatus,
} from "@/components/home/use-home-data";
import { useHomeKeys } from "@/components/home/use-home-keys";
import { useMediaQuery } from "@/components/home/use-media-query";
import Link from "@/components/smart-link";
import {
  collectionPollMs,
  getEffectiveBoardColor,
  getEffectiveCode62Glyph,
  getEffectiveDeviceType,
  queryKeys,
  useActivePage,
  useBoardCurrentMessage,
  useBoardSettings,
  usePagePreview,
  usePages,
  useStatus,
} from "@/hooks/use-board";
import { useHubConnection } from "@/hooks/use-hub-connection";
import { useSilence } from "@/hooks/use-silence";
import { useLocale, useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import type { Collection, DeviceType, SetTemporaryOverrideRequest } from "@/lib/api";
import { api, isCollectionId } from "@/lib/api";
import type { BoardGeometry } from "@/lib/board-characters-to-template";
import { classifyDimensions } from "@/lib/board-dimensions";
import { onLiveOutputMessageChange, readLiveOutputMessage, writeLiveOutputMessage } from "@/lib/live-output-channel";
import { isDisplayOffline } from "@/lib/status-banners";

export interface ActivePageDisplayProps {
  /** Opens Compose a message, the PageHeader's one entry (C, and the board menu). */
  onCompose?: () => void;
}

/**
 * Home's Now showing (07a §3, 03 `33:10`): FiestaUI's NowShowingCard hero with
 * the board, the mode badge, the Override Countdown and outcome sentence,
 * Change Page as the in-content secondary action, and the board context menu.
 * The one Compose entry is the PageHeader's (home.tsx); this card only calls
 * `onCompose` from its menu and the C key.
 */
export function ActivePageDisplay({ onCompose }: ActivePageDisplayProps = {}) {
  const t = useTranslations("activeDisplay");
  const tn = useTranslations("home.nowShowing");
  const tm = useTranslations("home.contextMenu");
  const tb = useTranslations("home.banners");
  const connection = useHubConnection();
  const sendsDisabled = !connection.deviceOnline || !connection.hubReachable;
  const currentSendsDisabled = useRef(sendsDisabled);
  useEffect(() => {
    currentSendsDisabled.current = sendsDisabled;
  }, [sendsDisabled]);
  const { data: fleetStatus } = useStatus();
  const phone = useMediaQuery("(max-width: 767px)");
  const tPause = useTranslations("displaySettings.pause");
  const navigate = useNavigate();
  const locale = useLocale();
  const refresh = useRefreshHomeStatus();

  // Current board selection (issue #1247). Queries are board-scoped only in
  // multi-board installs so single-board behavior is completely unchanged.
  const { currentBoardId, currentBoard, boards } = useCurrentBoard();
  const isMultiBoard = boards.length > 1;
  const scopedBoardId = isMultiBoard && currentBoardId ? currentBoardId : undefined;
  // Live board polling (and Live Output) only track the primary board, and
  // plugin triggers only ever drive it.
  const isPrimaryBoard = !scopedBoardId || scopedBoardId === boards[0]?.id;

  const [changePageOpen, setChangePageOpen] = useState(false);

  const { data: activeScheduleData } = useQuery({
    // Board-scoped key: the unscoped ["schedules", "active"] invalidations
    // used elsewhere still match it as a prefix.
    queryKey: scopedBoardId ? ["schedules", "active", scopedBoardId] : ["schedules", "active"],
    queryFn: () => api.getActiveSchedule(scopedBoardId),
    refetchInterval: (query) =>
      Math.min(60000, collectionPollMs(query.state.data?.resolved_next_check_seconds) || 60000),
  });
  const scheduleEnabled = activeScheduleData?.schedule_enabled || false;

  // H1: this display's own override. H2: when it next changes, and to what.
  const temporaryOverride = activeScheduleData?.temporary_override ?? null;
  const overrideActive = temporaryOverride?.active === true;
  const { data: boardDetail } = useBoardDetail(scopedBoardId);
  const { data: trigger } = useActiveTrigger(isPrimaryBoard && overrideActive);
  // S4: name the alert by its plugin's display name, not its id.
  const { data: pluginsData } = useQuery({
    queryKey: ["plugins"],
    queryFn: () => api.listPlugins(),
    enabled: !!trigger,
    staleTime: 5 * 60 * 1000,
  });
  const triggerPluginName = trigger
    ? (pluginsData?.plugins?.find((p) => p.id === trigger.plugin_id)?.name ?? trigger.plugin_id)
    : "";
  const overrideShowing = overrideOnScreen({ overrideActive, isPrimary: isPrimaryBoard, triggerActive: !!trigger });

  const { data: activePageData } = useActivePage(scopedBoardId);
  const silence = useSilence(scopedBoardId);
  const silenceStatus = silence.status;

  // Live Output (the editor's mirror) — seeded from localStorage, synced
  // across tabs.
  const queryClient = useQueryClient();
  const { data: liveOutputMessage } = useQuery<string | null>({
    queryKey: ["liveOutputMessage"],
    queryFn: () => null,
    staleTime: Infinity,
    initialData: () => readLiveOutputMessage(),
  });
  useEffect(() => {
    const current = readLiveOutputMessage();
    if (current !== null) {
      queryClient.setQueryData(["liveOutputMessage"], current);
    }
    return onLiveOutputMessageChange((msg) => {
      queryClient.setQueryData(["liveOutputMessage"], msg);
    });
  }, [queryClient]);

  // Turn off Live Mode from Home: the editor's inactivity timeout dies with
  // the editor, so without this kill switch Home would stay on Live Mode.
  const handleDisableLiveMode = useCallback(() => {
    queryClient.setQueryData(["liveOutputMessage"], null);
    writeLiveOutputMessage(null);
    api.forceRefresh().catch(() => {});
    toast.success(tn("toastLiveModeOff"));
  }, [queryClient, tn]);

  const { data: boardSettings } = useBoardSettings();
  const targetBoard = currentBoard ?? boardSettings?.boards?.[0];
  const displayName = targetBoard?.name ?? "";
  const isTargetPaused = targetBoard?.paused === true;
  const health = targetBoard ? fleetStatus?.boards?.[targetBoard.id]?.health : undefined;
  const displayOffline = isDisplayOffline(health);

  // Pause / resume (issue #2051), now in the board menu (07a §6).
  const pauseMutation = useMutation({
    mutationFn: ({ boardId, paused }: { boardId: string; paused: boolean }) => api.setBoardPaused(boardId, paused),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const { data: collectionsData } = useQuery({
    queryKey: ["collections"],
    queryFn: api.getCollections,
    staleTime: 5 * 60 * 1000,
  });
  const { data: pagesData } = usePages();
  const pages = useMemo(() => pagesData?.pages || [], [pagesData]);
  const nameOf = useCallback(
    (id: string | null | undefined) =>
      id
        ? (pages.find((p) => p.id === id)?.name ??
          collectionsData?.collections?.find((c: Collection) => c.id === id)?.name ??
          null)
        : null,
    [pages, collectionsData],
  );

  // Discard the message held until silence ends (#1944).
  const discardHeldMutation = useMutation({
    mutationFn: () => api.discardHeldSend(scopedBoardId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.silenceStatus() });
      toast.success(t("toastHeldDiscarded"));
    },
    onError: () => toast.error(t("toastHeldDiscardFailed")),
  });

  // What the Schedule or the manual pin puts on the display (an override aside).
  const activePageId = scheduleEnabled ? activeScheduleData?.page_id || null : activePageData?.page_id || null;
  const manualPageId = activePageData?.page_id || null;
  const activeCollection = useMemo(() => {
    if (!activePageId || !isCollectionId(activePageId)) return null;
    return collectionsData?.collections?.find((c: Collection) => c.id === activePageId) || null;
  }, [activePageId, collectionsData]);
  const activePage = useMemo(() => pages.find((p) => p.id === activePageId) || null, [pages, activePageId]);

  // Silence "page" mode freezes the board on the silence page (issue #1637).
  const silencePageId = silenceStatus?.active && silenceStatus.mode === "page" ? (silenceStatus.page_id ?? null) : null;
  const silencePage = useMemo(
    () => (silencePageId ? pages.find((p) => p.id === silencePageId) || null : null),
    [pages, silencePageId],
  );

  // The member page a collection is rendering now (issue #1513).
  const resolvedPageId = scheduleEnabled
    ? (activeScheduleData?.resolved_page_id ?? null)
    : (activePageData?.resolved_page_id ?? null);
  const resolvedCollectionPage = useMemo(
    () => (activeCollection && resolvedPageId ? pages.find((p) => p.id === resolvedPageId) || null : null),
    [activeCollection, resolvedPageId, pages],
  );

  // Cancel override (outline, never the filled primary), with the 07a
  // "Override canceled · Undo" toast for 10 s.
  // H1: every override call names its display, always (one rule, review S7).
  const overrideBoardId = scopedBoardId ?? targetBoard?.id;
  // Root's Toaster survives route changes. A retained action must not use
  // this mount's frozen connectivity after leaving Home. Display switches
  // keep the action's captured board ID while this Home is still mounted.
  const overrideUndoOwner = useRef<{ toastIds: Set<string> } | null>(null);
  useEffect(() => {
    const owner = { toastIds: new Set<string>() };
    overrideUndoOwner.current = owner;
    return () => {
      overrideUndoOwner.current = null;
      owner.toastIds.forEach((id) => toast.dismiss(id));
    };
  }, []);

  const cancelOverrideMutation = useMutation({
    mutationFn: ({
      boardId,
    }: {
      boardId: string | undefined;
      previous: typeof temporaryOverride;
      owner: typeof overrideUndoOwner.current;
    }) => api.clearTemporaryOverride(boardId),
    onSuccess: (_result, { boardId, previous, owner }) => {
      refresh();
      if (!owner || overrideUndoOwner.current !== owner) return;
      if (!currentSendsDisabled.current) nudgeDisplay(boardId);
      owner.toastIds.add(overrideUndoToastId(boardId));
      toast.info(tn("toastOverrideCanceled"), {
        id: overrideUndoToastId(boardId),
        duration: 10_000,
        action: previous?.active
          ? { label: tn("undo"), onClick: () => restoreOverride(previous, boardId, owner) }
          : undefined,
      });
    },
    onError: () => toast.error(tn("toastCancelFailed")),
  });

  // Undo puts the same hold back for the time it had left, on the same
  // display, with the same revert. It never overwrites a newer override (a
  // verb or another client may have set one inside the 10 s), and a hold
  // that would already have ended is not re-created (review S2). The bar
  // restarts: the hub stamps a new started_at.
  const restoreOverride = useCallback(
    async (
      previous: NonNullable<typeof temporaryOverride>,
      boardId: string | undefined,
      owner: NonNullable<typeof overrideUndoOwner.current>,
    ) => {
      if (currentSendsDisabled.current || overrideUndoOwner.current !== owner) return;
      let remainingMs = previous.expires_at ? new Date(previous.expires_at).getTime() - Date.now() : null;
      if (remainingMs !== null && remainingMs <= 0) {
        toast.info(tn("toastUndoEnded"));
        return;
      }
      try {
        const current = await api.getTemporaryOverride(boardId);
        if (currentSendsDisabled.current || overrideUndoOwner.current !== owner) return;
        if (current.active) {
          toast.info(tn("toastUndoNewer"));
          return;
        }
        // The status read may outlast the remaining hold. Check again at send.
        remainingMs = previous.expires_at ? new Date(previous.expires_at).getTime() - Date.now() : null;
        if (remainingMs !== null && remainingMs <= 0) {
          toast.info(tn("toastUndoEnded"));
          return;
        }
        const minutes = remainingMs !== null ? Math.max(1, Math.ceil(remainingMs / 60_000)) : undefined;
        const content: SetTemporaryOverrideRequest = previous.page_id
          ? { page_id: previous.page_id }
          : {
              template: previous.template ?? [],
              ...(previous.line_metadata ? { line_metadata: previous.line_metadata } : {}),
              ...(previous.device_type ? { device_type: previous.device_type } : {}),
              ...(previous.notes_wide ? { notes_wide: previous.notes_wide } : {}),
              ...(previous.notes_tall ? { notes_tall: previous.notes_tall } : {}),
              ...(previous.grid_rows ? { grid_rows: previous.grid_rows } : {}),
              ...(previous.grid_cols ? { grid_cols: previous.grid_cols } : {}),
            };
        await api.setTemporaryOverride({
          ...content,
          ...(boardId ? { board_id: boardId } : {}),
          ...(minutes !== undefined ? { duration_minutes: minutes } : {}),
          revert_mode: (previous.revert_mode ?? "schedule") as "schedule" | "blank" | "page",
          ...(previous.revert_page_id ? { revert_page_id: previous.revert_page_id } : {}),
        } as SetTemporaryOverrideRequest);
        refresh();
        if (!currentSendsDisabled.current && overrideUndoOwner.current === owner) nudgeDisplay(boardId);
      } catch {
        toast.error(tn("toastCancelFailed"));
      }
    },
    [refresh, tn],
  );

  // What the board shows (live state; Live Output on the primary).
  const { data: boardState } = useBoardCurrentMessage(scopedBoardId);
  const liveMessageForBoard = isPrimaryBoard ? (liveOutputMessage ?? null) : null;
  const needsPreviewFallback = !!scopedBoardId && !!boardState && boardState.message === null;
  const fallbackPageId = needsPreviewFallback && activePageId && !isCollectionId(activePageId) ? activePageId : null;
  const { data: fallbackPreview } = usePagePreview(fallbackPageId, { enabled: needsPreviewFallback });

  // The full geometry from the live board's dimensions, falling back to the
  // selected board's settings (note arrays render their true W×H; a
  // FiestaPanel's family comes from the board itself).
  const activeGeometry = useMemo((): BoardGeometry => {
    if (currentBoard?.device_type === "panel") {
      return {
        deviceType: "panel",
        notesWide: 1,
        notesTall: 1,
        gridRows: boardState?.rows || currentBoard.grid_rows || undefined,
        gridCols: boardState?.cols || currentBoard.grid_cols || undefined,
      };
    }
    if (boardState?.rows && boardState?.cols) {
      try {
        const classified = classifyDimensions(boardState.rows, boardState.cols);
        if (classified.device_type === "note" && currentBoard?.device_type === "note_array") {
          return {
            deviceType: "note_array",
            notesWide: currentBoard.notes_wide ?? 1,
            notesTall: currentBoard.notes_tall ?? 1,
          };
        }
        return {
          deviceType: classified.device_type as DeviceType,
          notesWide: classified.notes_wide ?? 1,
          notesTall: classified.notes_tall ?? 1,
        };
      } catch {
        // Unclassifiable dims (defensive) — fall through to board settings.
      }
    }
    if (currentBoard?.device_type) {
      return {
        deviceType: currentBoard.device_type,
        notesWide: currentBoard.notes_wide ?? 1,
        notesTall: currentBoard.notes_tall ?? 1,
      };
    }
    return { deviceType: getEffectiveDeviceType(boardSettings), notesWide: 1, notesTall: 1 };
  }, [boardState, currentBoard, boardSettings]);

  // Last known must come from a confirmed board frame, never a local mirror or rendered page.
  const confirmedOnly = sendsDisabled || displayOffline;
  const localLiveMessage = confirmedOnly ? null : liveMessageForBoard;
  const displayMessage =
    localLiveMessage ?? boardState?.message ?? (confirmedOnly ? null : fallbackPreview?.message) ?? null;
  const displayCells =
    !localLiveMessage && boardState?.message != null ? (boardState.cells as BoardCellGrid | undefined) : undefined;
  const displayLayers = !localLiveMessage && boardState?.message != null ? boardState.layers : undefined;

  // ── What the card says ────────────────────────────────────────────────
  const overridePageId = overrideActive ? (temporaryOverride?.page_id ?? null) : null;
  const overrideTitle = overrideActive ? (nameOf(overridePageId) ?? tn("composedMessage")) : null;
  const now = new Date();
  const nextChangeAt = boardDetail?.next_change_at ? new Date(boardDetail.next_change_at) : null;
  const nextPageName = nameOf(boardDetail?.next_page_id);

  let mode: NowShowingMode | undefined;
  let title: string;
  let outcome: string | undefined;
  let note: string | null = null;
  if (overrideActive && !overrideShowing) {
    // A plugin alert covers the override (H1 review carry): say so, and
    // claim neither the Override nor its page on screen.
    mode = undefined;
    title = tn("triggerTitle", { plugin: triggerPluginName });
    note = tn("triggerDescription", { page: overrideTitle ?? "" });
  } else if (overrideShowing) {
    mode = "override";
    title = overrideTitle ?? "";
    const expires = temporaryOverride?.expires_at ? new Date(temporaryOverride.expires_at) : null;
    if (!expires) outcome = tn("overrideOutcomeUntilCancel");
    else if (!scheduleEnabled && nameOf(manualPageId))
      outcome = tn("overrideOutcomeManual", { time: formatClock(expires, locale), page: nameOf(manualPageId) ?? "" });
    else if (nextPageName && boardDetail?.next_change_reason === "override_ends")
      outcome = tn("overrideOutcomeNext", { time: formatClock(expires, locale), page: nextPageName });
    else outcome = tn("overrideOutcome", { time: formatClock(expires, locale) });
  } else {
    // Live Mode (the editor's mirror) drives the board, not the Schedule or
    // the pin, so no mode is claimed while it is on.
    mode = liveMessageForBoard ? undefined : scheduleEnabled ? "schedule" : "manual";
    // BB-A-14: in a Schedule gap the board keeps what it last showed; say
    // that in plain words rather than the hub's gap reason.
    const gap = scheduleEnabled && !silencePage && !activeCollection && !activePage;
    title = silencePage?.name ?? activeCollection?.name ?? activePage?.name ?? (gap ? tn("scheduleGap") : tn("noPage"));
    if (scheduleEnabled) {
      const scheduleChange = boardDetail?.next_change_reason === "schedule" && nextChangeAt && nextChangeAt > now;
      if (gap)
        outcome = scheduleChange
          ? tn("scheduleGapUntil", { time: formatClock(nextChangeAt, locale) })
          : tn("scheduleGapKeeps");
      else
        outcome = scheduleChange
          ? nextPageName
            ? tn("scheduleNext", { time: formatClock(nextChangeAt, locale), page: nextPageName })
            : tn("scheduleUntil", { time: formatClock(nextChangeAt, locale) })
          : tn("scheduleRunning");
    } else {
      const page = activeCollection?.name ?? activePage?.name;
      outcome = page ? tn("manual", { page }) : tn("manualNoPage");
    }
  }

  // Edit page: the page on the board (07a: action row, board menu, E).
  const editHref = (() => {
    if (overrideActive && overrideShowing) {
      if (!overridePageId) return null;
      return isCollectionId(overridePageId)
        ? `/collections/${encodeURIComponent(overridePageId)}`
        : `/pages/edit/${overridePageId}`;
    }
    if (overrideActive) return null;
    if (silencePage) return `/pages/edit/${silencePage.id}`;
    // A collection is edited from its own link; Edit page opens the member
    // page on the board now, when the hub names it.
    if (activeCollection) return resolvedCollectionPage ? `/pages/edit/${resolvedCollectionPage.id}` : null;
    if (activePage) return `/pages/edit/${activePage.id}`;
    return null;
  })();

  const openChangePage = useCallback(() => {
    if (!sendsDisabled) setChangePageOpen(true);
  }, [sendsDisabled]);
  const compose = useCallback(() => {
    if (!sendsDisabled) onCompose?.();
  }, [onCompose, sendsDisabled]);
  useHomeKeys({
    onCompose: compose,
    onChangePage: openChangePage,
    onEditPage: editHref ? () => navigate(editHref) : null,
  });

  const boardText = boardDetail?.text ?? null;
  const copyText = boardText
    ? () => {
        navigator.clipboard
          ?.writeText(boardText)
          .then(() => toast.success(tm("toastCopied")))
          .catch(() => toast.error(tm("toastCopyFailed")));
      }
    : null;
  const refreshBoard = () => {
    if (sendsDisabled) return;
    api
      .restoreBoard(scopedBoardId)
      .then(() => {
        refresh();
        toast.success(tm("toastRefreshed", { board: displayName }));
      })
      .catch(() => toast.error(tm("toastRefreshFailed", { board: displayName })));
  };

  const countdownEndsAt =
    overrideShowing && temporaryOverride?.expires_at ? new Date(temporaryOverride.expires_at) : null;
  const countdownStartedAt = temporaryOverride?.started_at ?? boardDetail?.override_started_at ?? null;

  const description = (
    <Text as="span" size="sm" tone="muted" className="flex flex-wrap items-center gap-2">
      {note && <Text as="span">{note}</Text>}
      {!note && activeCollection && !overrideActive && (
        // A Collection decides which member page shows (issue #1513): link
        // the collection's logic and the member page on the board now.
        <Text as="span" data-testid="home-collection-line">
          <Link
            href={`/collections/${encodeURIComponent(activeCollection.id)}`}
            className="font-medium text-foreground underline-offset-2 hover:underline hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
            aria-label={t("editCollection", { collectionName: activeCollection.name })}
          >
            {t("collectionBadge")}
          </Link>
          {resolvedCollectionPage && (
            <>
              <ChevronRight className="mx-0.5 inline size-3" aria-hidden="true" />
              <Link
                href={`/pages/edit/${resolvedCollectionPage.id}`}
                className="font-medium text-foreground underline-offset-2 hover:underline hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
                aria-label={t("editActivePage", { pageName: resolvedCollectionPage.name })}
              >
                {resolvedCollectionPage.name}
              </Link>
            </>
          )}
        </Text>
      )}
      {liveMessageForBoard && (
        <Badge
          variant="destructive"
          className="animate-pulse"
          onDismiss={handleDisableLiveMode}
          dismissLabel={tn("turnOffLiveMode")}
        >
          <Radio className="inline h-3 w-3 mr-1 align-[-2px]" aria-hidden="true" />
          {tn("liveMode")}
        </Badge>
      )}
      {silenceStatus?.active && <Badge variant="secondary">{tb("silenced")}</Badge>}
      {isTargetPaused && (
        <Badge
          variant="default"
          className="gap-1 bg-warning text-warning-foreground hover:bg-warning"
          data-testid="board-paused-badge"
          title={tPause("tooltip")}
        >
          <Pause className="h-3 w-3" aria-hidden="true" />
          {tPause("badge")}
        </Badge>
      )}
    </Text>
  );
  const hasDescription =
    !!note ||
    (!!activeCollection && !overrideActive) ||
    !!liveMessageForBoard ||
    !!silenceStatus?.active ||
    isTargetPaused;

  const actions = (
    <Flex align="center" gap="3" wrap className="w-full">
      <Button
        variant="secondary"
        disabled={sendsDisabled}
        onClick={openChangePage}
        className="gap-2 max-sm:flex-1 max-sm:h-11"
      >
        <LayoutGrid className="size-4" aria-hidden="true" />
        {tn("changePage")}
      </Button>
      {overrideActive && (
        <Button
          variant="outline"
          onClick={() =>
            cancelOverrideMutation.mutate({
              boardId: overrideBoardId,
              previous: temporaryOverride,
              owner: overrideUndoOwner.current,
            })
          }
          disabled={sendsDisabled || cancelOverrideMutation.isPending}
          className="max-sm:flex-1 max-sm:h-11"
        >
          {tn("cancelOverride")}
        </Button>
      )}
      {mode === "schedule" ? (
        <Button variant="ghost" asChild className="gap-2 max-sm:hidden">
          <Link href="/schedule">
            <Calendar className="size-4" aria-hidden="true" />
            {tn("viewSchedule")}
          </Link>
        </Button>
      ) : editHref ? (
        <Button variant="ghost" asChild className="gap-2 max-sm:hidden">
          <Link href={editHref}>
            <PencilLine className="size-4" aria-hidden="true" />
            {tn("editPage")}
          </Link>
        </Button>
      ) : null}
      {/* 07a key hints. Hidden on touch, where there is no keyboard to press. */}
      <Flex
        align="center"
        gap="1.5"
        className="hidden text-xs text-muted-foreground sm:flex pointer-coarse:hidden"
        aria-hidden="true"
        data-testid="home-key-hints"
      >
        <Kbd>C</Kbd>
        {tn("keyCompose")}
        <Kbd className="ms-1.5">P</Kbd>
        {tn("keyChangePage")}
      </Flex>
    </Flex>
  );

  const modeLabel = (m: NowShowingMode | undefined) =>
    m === "override" ? tn("modeOverride") : m === "manual" ? tn("modeManual") : m ? tn("modeSchedule") : null;
  const boardActions: BoardActions = {
    boardName: displayName,
    // 07a `310:33402`: the touch sheet's "<page> · <mode>" line.
    summary: [title, modeLabel(mode)].filter(Boolean).join(" · "),
    onChangePage: openChangePage,
    onCompose: compose,
    editHref,
    onCopyText: copyText,
    onRefresh: refreshBoard,
    paused: isTargetPaused,
    onTogglePause: targetBoard
      ? () => pauseMutation.mutate({ boardId: targetBoard.id, paused: !isTargetPaused })
      : null,
    busy: sendsDisabled || pauseMutation.isPending,
    sendsDisabled,
  };

  const outOfSync =
    !!boardState &&
    ((boardState.characters != null &&
      boardState.expected_characters != null &&
      JSON.stringify(boardState.characters) !== JSON.stringify(boardState.expected_characters)) ||
      !!boardState.overwritten_at);
  const recoverableOutOfSync =
    outOfSync && !silence.active && !liveMessageForBoard && !sendsDisabled && !displayOffline;
  const heldTime = silence.held?.queued_at ? new Date(silence.held.queued_at) : null;
  const heldCard =
    silence.active && silence.held ? (
      <Card className="gap-3 p-4 md:p-5" data-testid="home-held-message">
        <CardTitle className="font-mono text-xs font-medium uppercase text-brand">
          {heldTime && Number.isFinite(heldTime.getTime())
            ? tb("heldAt", { time: formatClock(heldTime, locale) })
            : tb("heldTitle")}
        </CardTitle>
        <Text size="sm" className="font-semibold">
          {tb("heldPreview", { preview: silence.held.preview })}
        </Text>
        <Text size="sm" tone="muted">
          {silence.until
            ? tb(scheduleEnabled ? "heldBody" : "heldManualBody", { board: displayName, time: silence.until })
            : tb(scheduleEnabled ? "heldNoTime" : "heldManualNoTime")}
        </Text>
        {/* The hub has no release-held-now endpoint; hide that action, per 07a. */}
        <Button
          variant="outline"
          size="sm"
          disabled={sendsDisabled || discardHeldMutation.isPending}
          onClick={() => {
            if (!sendsDisabled) discardHeldMutation.mutate();
          }}
          className="self-start max-md:min-h-11"
        >
          {tb("discard")}
        </Button>
      </Card>
    ) : null;

  const cardMode = sendsDisabled || displayOffline || silence.active ? undefined : mode;
  const phoneModeBadge = cardMode ? (
    <Badge variant={cardMode === "override" ? "default" : "secondary"} className="font-sans">
      {modeLabel(cardMode)}
    </Badge>
  ) : null;
  const boardElement = (
    <BoardContextMenu actions={boardActions}>
      {/* TODO(FiestaUI G4): add a board-only last-known state. Dim the hardware
                  picture, keeping viewport controls and scroll instructions at full contrast. */}
      <Flex
        justify="center"
        data-testid="home-board-state"
        className={
          sendsDisabled
            ? "overflow-x-hidden [&_[data-slot=board-viewport-bezel]]:opacity-50 [&_[data-slot=led-matrix-display]]:opacity-50"
            : displayOffline
              ? "overflow-x-hidden [&_[data-slot=board-viewport-bezel]]:opacity-60 [&_[data-slot=led-matrix-display]]:opacity-60"
              : "overflow-x-hidden"
        }
        style={{ contain: "layout style paint" }}
      >
        {/* Keyed per display (BB-A-2): a switch mounts a fresh board, whose
            first paint lands at once instead of flapping from the last display. */}
        <HomeBoard
          key={(currentBoard ?? boardSettings?.boards?.[0])?.id ?? "primary"}
          board={currentBoard ?? boardSettings?.boards?.[0]}
          geometry={activeGeometry}
          message={displayMessage}
          cells={displayCells}
          layers={displayLayers}
          isLoading={!boardState && !liveMessageForBoard}
          size="md"
          // 07a hero placements (DD-W61): Tile sm edge to edge on a phone;
          // above it the medium hero, whose bezel hugs a board that fits and
          // settles a near fit to fill it, not a full-width slab with black
          // side margins (BB-FH-12).
          layout={phone ? "phone-hero" : "medium-hero"}
          fallbackColor={getEffectiveBoardColor(boardSettings)}
          fallbackGlyph={getEffectiveCode62Glyph(boardSettings)}
        />
      </Flex>
    </BoardContextMenu>
  );

  return (
    <Stack gap="4" {...anchorProps("home.active-display")}>
      {phone && heldCard}

      {scheduleEnabled && !activePageId && !overrideActive && (
        <Alert variant="default" className="border-warning/50 bg-warning/10">
          <AlertTriangle className="h-4 w-4 text-warning" />
          <AlertDescription className="text-sm">
            {t("noPageScheduled")}{" "}
            <Link
              href="/schedule"
              className="underline font-medium hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded"
            >
              {t("scheduleSettingsLink")}
            </Link>
            .
          </AlertDescription>
        </Alert>
      )}

      {/* Another app wrote to the board (issue #1945). */}
      <BoardOutOfSyncBanner
        boardId={scopedBoardId}
        geometry={activeGeometry}
        paused={isTargetPaused}
        suppressed={!!liveMessageForBoard || sendsDisabled || displayOffline}
        home={{ display: displayName, pageName: title }}
      />

      <Box
        className="grid grid-cols-1 min-w-0 gap-4 lg:gap-5 lg:grid-cols-[minmax(0,1fr)_274px] items-start"
        data-testid="home-columns"
      >
        {phone && (
          // 07a `306:53086`: the board leads on a phone, edge to edge (the
          // page gutter is bled), in the kit's phone-hero placement so a
          // 22-column Flagship shows whole (BB-A-6).
          <Box className="-mx-4 min-w-0" data-testid="home-phone-board">
            {boardElement}
          </Box>
        )}
        <NowShowingCard
          display={displayName}
          meta={
            <Text as="span" size="xs" tone="muted" className="inline-flex items-center gap-2 font-mono">
              {/* 07a `306:53086`: on a phone the mode sits in the header and
                  the title takes the whole line below (BB-A-16); the board
                  needs no type-and-size row there (BB-A-6). */}
              {phone ? phoneModeBadge : boardMeta(targetBoard, activeGeometry)}
              <BoardActionsMenu actions={boardActions} />
            </Text>
          }
          className="group/home-card min-w-0"
          title={title}
          headingLevel={2}
          mode={phone ? undefined : cardMode}
          status={sendsDisabled ? "neutral" : displayOffline ? "danger" : recoverableOutOfSync ? "warning" : "success"}
          labels={{
            nowShowing: recoverableOutOfSync ? tb("shouldShow") : tn("label"),
            modes: { schedule: tn("modeSchedule"), manual: tn("modeManual"), override: tn("modeOverride") },
          }}
          data-testid="now-showing"
          board={phone ? null : boardElement}
          description={
            sendsDisabled || displayOffline ? (
              <>
                <Badge variant={sendsDisabled ? "outline" : "destructive"}>
                  {sendsDisabled ? tb("lastKnown") : tb("offline")}
                </Badge>
                {sendsDisabled && connection.lastContactAt ? (
                  <Text as="span" size="sm" className="ms-2">
                    {tb("asOf", { board: displayName, time: formatClock(new Date(connection.lastContactAt), locale) })}
                  </Text>
                ) : null}
              </>
            ) : hasDescription ? (
              description
            ) : undefined
          }
          countdown={
            countdownEndsAt && !sendsDisabled && !displayOffline ? (
              <Countdown
                endsAt={countdownEndsAt}
                startedAt={countdownStartedAt ? new Date(countdownStartedAt) : undefined}
                labels={{
                  remaining: (ms) => tn("remaining", { time: formatSpan(ms) }),
                  until: (time) => tn("until", { time }),
                  ended: tn("ended"),
                  endedAnnouncement: tn("endedAnnouncement"),
                }}
                locale={locale}
                onEnd={refresh}
                data-testid="override-countdown"
              />
            ) : undefined
          }
          outcome={
            sendsDisabled
              ? tb("sendsPaused")
              : displayOffline
                ? health?.last_connected_at
                  ? tb("offlineMeta", { time: formatClock(new Date(health.last_connected_at), locale) })
                  : tb("offlineNever")
                : recoverableOutOfSync
                  ? [outcome, tb("outOfSyncOutcome", { page: title })].filter(Boolean).join(" ")
                  : outcome
          }
          actions={actions}
        />

        <HomeSupportingPane
          board={targetBoard}
          scheduleEnabled={activeScheduleData?.schedule_enabled}
          detail={boardDetail}
          pageName={nameOf(activePageId)}
          nameOf={nameOf}
          refresh={refresh}
          leading={phone ? undefined : heldCard}
        />
      </Box>

      <ChangePageDialog
        open={changePageOpen}
        onOpenChange={setChangePageOpen}
        board={targetBoard}
        isPrimary={isPrimaryBoard}
        scheduleEnabled={scheduleEnabled}
        currentPageId={overrideShowing ? overridePageId : activePageId}
        manualPageName={nameOf(manualPageId)}
        overrideName={overrideActive ? overrideTitle : null}
        nextChange={scheduleNextChange(boardDetail, now)}
        silence={silence.active ? { until: silence.until } : null}
      />
    </Stack>
  );
}
