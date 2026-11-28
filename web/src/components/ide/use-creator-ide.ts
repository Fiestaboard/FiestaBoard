"use client";

import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { type RefObject, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useCurrentBoard } from "@/components/current-board-context";
import type { PageBuilderHandle } from "@/components/page-builder";
import { useCollections, usePages } from "@/hooks/use-board";
import type { CurrentPageSnapshot } from "@/lib/ai-chat-types";
import { api, ApiError, type PageUpdate } from "@/lib/api";
import { type IdeTemplateTarget, type PageContent, type PageDraft, pageHistoryApi } from "@/lib/api/page-history";
import { deriveEditState, derivePreviewDisplay } from "@/lib/ide/edit-state";
import { problemsFromValidation, warningsFromCharset } from "@/lib/ide/problems";
import { pageDisplayIds, showsOnModel } from "@/lib/ide/shows-on";

export const ideKeys = {
  draft: (pageId: string) => ["ide", "draft", pageId] as const,
  revisions: (pageId: string) => ["ide", "revisions", pageId] as const,
  revision: (pageId: string, id: string) => ["ide", "revision", pageId, id] as const,
  sends: (pageId: string) => ["ide", "sends", pageId] as const,
  schedules: ["ide", "schedules"] as const,
  active: (boardId: string) => ["ide", "active", boardId] as const,
  validate: (key: string) => ["ide", "validate", key] as const,
  render: (key: string) => ["ide", "render", key] as const,
};

/** How often the IDE re-reads the editor's state (unsaved, mirroring, content). */
export const BUILDER_POLL_MS = 1000;
/** Quiet time after typing before the Problems console re-validates. */
export const VALIDATE_DEBOUNCE_MS = 600;
/** H8 and H9b reads refresh on this cadence while the editor is open. */
export const HUB_REFRESH_MS = 60_000;
/** D4: unsaved edits reach the hub draft this long after the last change. */
export const AUTOSAVE_MS = 1500;

interface BuilderState {
  unsaved: boolean;
  mirroring: boolean;
  snapshot: CurrentPageSnapshot | null;
  /** The display the editor previews the page as: the page's own display (UX-6-1). */
  previewBoardId: string | null;
}

/** The content a draft and the editor are compared on. */
export function contentKey(content: Pick<PageContent, "name" | "template" | "line_metadata"> | null | undefined) {
  if (!content) return "";
  return JSON.stringify([content.name, content.template ?? [], content.line_metadata ?? []]);
}

/**
 * Everything a draft holds, for deciding whether the editor and a draft agree
 * (D4): text and line metadata, and also geometry, transition and canvases,
 * so a draw-mode, retarget or Page-tab edit is autosaved too (FABLE-2583, UX-7-1).
 */
export function draftContentKey(content: CurrentPageSnapshot | PageContent | null | undefined): string {
  if (!content) return "";
  const body = draftBodyFromSnapshot(content as CurrentPageSnapshot);
  return JSON.stringify([
    body.name,
    body.template ?? [],
    body.line_metadata ?? [],
    body.device_type ?? null,
    body.notes_wide ?? null,
    body.notes_tall ?? null,
    body.grid_rows ?? null,
    body.grid_cols ?? null,
    body.canvases ?? null,
    body.transition_strategy ?? null,
    body.duration_seconds ?? null,
  ]);
}

/** The PageUpdate a Save draft writes from the editor's current content. */
export function draftBodyFromSnapshot(snapshot: CurrentPageSnapshot): PageUpdate {
  const body: PageUpdate = {
    name: snapshot.name,
    template: snapshot.template,
    line_metadata: snapshot.line_metadata,
  };
  if (snapshot.device_type) body.device_type = snapshot.device_type;
  if (snapshot.device_type === "note_array") {
    body.notes_wide = snapshot.notes_wide;
    body.notes_tall = snapshot.notes_tall;
  }
  if (snapshot.device_type === "panel") {
    body.grid_rows = snapshot.grid_rows;
    body.grid_cols = snapshot.grid_cols;
  }
  if (snapshot.canvases) body.canvases = snapshot.canvases.length ? snapshot.canvases : null;
  if (snapshot.transition_strategy !== undefined) body.transition_strategy = snapshot.transition_strategy;
  // UX-7-1: the Page tab's duration is staged page content, so the draft holds it too.
  if (snapshot.duration_seconds !== undefined) body.duration_seconds = snapshot.duration_seconds;
  return body;
}

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

/**
 * A query has its answer for this editing session: loaded, and not re-asking.
 * Cached data is not pending, but a reopened editor refetches it on mount; the
 * page's displays are held once, so they wait for that answer (OPUS-2647 M1).
 */
const answered = (query: { isPending: boolean; isFetching: boolean }) => !query.isPending && !query.isFetching;

const nullOn404 = <T>(promise: Promise<T>) =>
  promise.catch((error: unknown) => {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  });

/**
 * Everything the Creator IDE reads and writes for one saved page: the
 * editor's own state (polled through its handle), H9a draft and versions,
 * H9b sends, H8 answers per display, and H4 board-width validation.
 */
export function useCreatorIde(pageId: string, builderRef: RefObject<PageBuilderHandle | null>, savedTick: number) {
  const queryClient = useQueryClient();
  const { boards, isLoading: boardsLoading } = useCurrentBoard();
  const [builder, setBuilder] = useState<BuilderState>({
    unsaved: false,
    mirroring: false,
    snapshot: null,
    previewBoardId: null,
  });

  useEffect(() => {
    const read = () => {
      const handle = builderRef.current;
      if (!handle) return;
      const next: BuilderState = {
        unsaved: handle.hasUnsavedChanges(),
        mirroring: handle.isMirroring(),
        snapshot: handle.getCurrentPage() ?? null,
        previewBoardId: handle.getPreviewBoardId(),
      };
      setBuilder((previous) =>
        previous.unsaved === next.unsaved &&
        previous.mirroring === next.mirroring &&
        previous.previewBoardId === next.previewBoardId &&
        JSON.stringify(previous.snapshot) === JSON.stringify(next.snapshot)
          ? previous
          : next,
      );
    };
    read();
    const timer = setInterval(read, BUILDER_POLL_MS);
    return () => clearInterval(timer);
  }, [builderRef]);

  const pages = usePages();
  const collections = useCollections();
  const draft = useQuery({
    queryKey: ideKeys.draft(pageId),
    // Most pages have no draft: check the hub's list first, so opening one
    // isn't a 404 in the console every time (BB-B-27).
    queryFn: async () => {
      const { drafts } = await pageHistoryApi.listDrafts();
      if (!drafts.some((entry) => entry.page_id === pageId)) return null;
      return nullOn404(pageHistoryApi.getDraft(pageId));
    },
    retry: false,
  });
  const revisions = useQuery({
    queryKey: ideKeys.revisions(pageId),
    queryFn: () => pageHistoryApi.listRevisions(pageId),
    retry: false,
  });
  const sends = useQuery({
    queryKey: ideKeys.sends(pageId),
    queryFn: () => pageHistoryApi.listSends(pageId),
    refetchInterval: HUB_REFRESH_MS,
    retry: false,
  });
  const schedules = useQuery({
    queryKey: ideKeys.schedules,
    queryFn: () => api.getSchedules("*"),
    retry: false,
  });
  const { answers: activeAnswers, settled: activeSettled } = useQueries({
    queries: boards.map((board) => ({
      queryKey: ideKeys.active(board.id),
      queryFn: () => api.getActiveSchedule(board.id),
      refetchInterval: HUB_REFRESH_MS,
      retry: false,
    })),
    combine: (results) => ({
      answers: results.map((result) => result.data),
      settled: results.every(answered),
    }),
  });

  const snapshot = builder.snapshot;
  // The page's own display is the one the editor previews it as (its
  // retarget, live-output target, else the sidebar's board when the page fits
  // it, else a display it fits), so the IDE never speaks for the sidebar's
  // board on a page that isn't on it (UX-6-1).
  const pageBoard = boards.find((board) => board.id === builder.previewBoardId) ?? null;
  const pageBoardId = pageBoard?.id ?? null;
  const target: IdeTemplateTarget | null = useMemo(
    () =>
      snapshot
        ? {
            template: snapshot.template,
            line_metadata: snapshot.line_metadata,
            device_type: snapshot.device_type,
            ...(snapshot.device_type === "note_array" && {
              notes_wide: snapshot.notes_wide,
              notes_tall: snapshot.notes_tall,
            }),
            ...(snapshot.device_type === "panel" && { grid_rows: snapshot.grid_rows, grid_cols: snapshot.grid_cols }),
            ...(pageBoardId && { board_id: pageBoardId }),
          }
        : null,
    [snapshot, pageBoardId],
  );
  const targetKey = useDebounced(target ? JSON.stringify(target) : "", VALIDATE_DEBOUNCE_MS);
  const validation = useQuery({
    queryKey: ideKeys.validate(targetKey),
    queryFn: () => pageHistoryApi.validateAtBoard(JSON.parse(targetKey) as IdeTemplateTarget),
    enabled: !!targetKey,
    placeholderData: (previous) => previous,
    retry: false,
  });
  const render = useQuery({
    queryKey: ideKeys.render(targetKey),
    queryFn: () => pageHistoryApi.renderAtBoard(JSON.parse(targetKey) as IdeTemplateTarget),
    enabled: !!targetKey && !!pageBoardId,
    placeholderData: (previous) => previous,
    retry: false,
  });

  const activeByBoard = useMemo(
    () => Object.fromEntries(boards.map((board, index) => [board.id, activeAnswers[index]])),
    [boards, activeAnswers],
  );
  const showsOn = useMemo(
    () =>
      showsOnModel({
        pageId,
        schedules: schedules.data?.schedules ?? [],
        collections: collections.data?.collections ?? [],
        boards,
        active: activeByBoard,
        defaultBoardId: boards[0]?.id,
      }),
    [pageId, schedules.data, collections.data, boards, activeByBoard],
  );
  // Handed to the editor so it previews the page as a display that shows it
  // (UX-6-1); a string key keeps the array stable between polls. Chosen once
  // per page, from the first settled answers (fresh ones: a reopened editor
  // re-asks for what it cached, see `answered`): "showing now" changes with the
  // clock (re-asked every minute), and the preview, its checks and the default
  // Mirror target must not move while you edit (OPUS-2645 S2). Picking a
  // live-output target or a retarget in the editor still wins over these.
  const displaysSettled = !boardsLoading && answered(schedules) && answered(collections) && activeSettled;
  const liveDisplaysKey = pageDisplayIds(showsOn).join("\n");
  const [heldDisplays, setHeldDisplays] = useState<{ pageId: string; key: string } | null>(null);
  if (displaysSettled && heldDisplays?.pageId !== pageId) setHeldDisplays({ pageId, key: liveDisplaysKey });
  const pageDisplaysKey = heldDisplays?.pageId === pageId ? heldDisplays.key : "";
  const pageDisplays = useMemo(() => (pageDisplaysKey ? pageDisplaysKey.split("\n") : []), [pageDisplaysKey]);

  const hubDraft: PageDraft | null = draft.data ?? null;
  const unsavedBeyondDraft =
    builder.unsaved && (!hubDraft || draftContentKey(hubDraft.content) !== draftContentKey(snapshot));
  const editState = deriveEditState({
    unsaved: unsavedBeyondDraft,
    hasDraft: !!hubDraft,
    mirroring: builder.mirroring,
  });
  const display = derivePreviewDisplay(showsOn.showingNow.length > 0, showsOn.scheduled);
  const problems = problemsFromValidation(validation.data?.errors ?? []);
  const warnings = warningsFromCharset(render.data?.charset_issues);

  const invalidateHistory = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: ideKeys.draft(pageId) });
    void queryClient.invalidateQueries({ queryKey: ideKeys.revisions(pageId) });
  }, [queryClient, pageId]);

  // The draft revisions this editor session wrote. Only those may be discarded
  // after the editor saves the page itself; a draft saved on another device or
  // made by Restore stays (the hub marks it stale).
  // State, not a ref: the header meta reads it to say whether autosave is on.
  const [ownedDraftRevisions, setOwnedDraftRevisions] = useState<ReadonlySet<string>>(() => new Set());
  const own = useCallback(
    (revision: string) =>
      setOwnedDraftRevisions((current) => (current.has(revision) ? current : new Set(current).add(revision))),
    [],
  );
  const [draftConflict, setDraftConflict] = useState(false);
  const saveDraft = useMutation({
    /** `overwrite` drops the revision guard: only after the reader chose Replace. */
    mutationFn: ({ overwrite = false }: { overwrite?: boolean } = {}) => {
      const current = builderRef.current?.getCurrentPage();
      if (!current) throw new Error("editor not ready");
      const known = queryClient.getQueryData<PageDraft | null>(ideKeys.draft(pageId));
      return pageHistoryApi.saveDraft(pageId, {
        ...draftBodyFromSnapshot(current),
        ...(known && !overwrite && { expected_revision: known.revision }),
      });
    },
    onSuccess: (saved) => {
      own(saved.revision);
      setDraftConflict(false);
      queryClient.setQueryData(ideKeys.draft(pageId), saved);
    },
    onError: (error) => {
      // 412: another device saved the draft since this editor read it. Ask; never retry on our own.
      if (error instanceof ApiError && error.status === 412) {
        setDraftConflict(true);
        void queryClient.invalidateQueries({ queryKey: ideKeys.draft(pageId) });
      }
    },
  });
  const discardDraft = useMutation({
    mutationFn: () => pageHistoryApi.discardDraft(pageId, hubDraft?.revision),
    onSuccess: () => queryClient.setQueryData(ideKeys.draft(pageId), null),
  });

  // D4 (BB-E-17): a draft the hub holds when the page opens is restored into
  // the editor ("Draft restored · Discard"); from then on this session owns it.
  const [restored, setRestored] = useState<{ revision: string; stale: boolean } | null>(null);
  const [restoreChecked, setRestoreChecked] = useState(false);
  // Only a successful read decides: after a failed one there may well be a
  // draft we cannot see, and writing blind would replace it (FABLE-2583).
  if (!restoreChecked && draft.isSuccess && snapshot) {
    setRestoreChecked(true);
    if (hubDraft && !builder.unsaved && draftContentKey(hubDraft.content) !== draftContentKey(snapshot)) {
      setRestored({ revision: hubDraft.revision, stale: hubDraft.stale });
      own(hubDraft.revision);
    }
  }
  // A draft that already matches the editor is this session's to keep in step.
  const draftInStep = !!hubDraft && draftContentKey(hubDraft.content) === draftContentKey(snapshot);
  if (restoreChecked && hubDraft && draftInStep && !ownedDraftRevisions.has(hubDraft.revision)) {
    own(hubDraft.revision);
  }
  const appliedRestore = useRef<string | null>(null);
  useEffect(() => {
    if (!restored || appliedRestore.current === restored.revision) return;
    const pending = queryClient.getQueryData<PageDraft | null>(ideKeys.draft(pageId));
    if (!pending || pending.revision !== restored.revision) return;
    appliedRestore.current = restored.revision;
    builderRef.current?.applyContent(pending.content);
  }, [restored, queryClient, pageId, builderRef]);

  const discardRestored = useCallback(async () => {
    const pending = queryClient.getQueryData<PageDraft | null>(ideKeys.draft(pageId));
    if (pending) await pageHistoryApi.discardDraft(pageId, pending.revision).catch(() => undefined);
    queryClient.setQueryData(ideKeys.draft(pageId), null);
    setRestored(null);
    invalidateHistory();
    await builderRef.current?.discardContent();
  }, [queryClient, pageId, builderRef, invalidateHistory]);

  /** The leave guard's "Discard changes": drop the draft this session owns, if any. */
  const discardOwnedDraft = useCallback(async () => {
    const pending = queryClient.getQueryData<PageDraft | null>(ideKeys.draft(pageId));
    if (!pending || !ownedDraftRevisions.has(pending.revision)) return;
    await pageHistoryApi.discardDraft(pageId, pending.revision).catch(() => undefined);
    queryClient.setQueryData(ideKeys.draft(pageId), null);
  }, [queryClient, pageId, ownedDraftRevisions]);

  // D4 autosave: unsaved edits go to the hub draft, never the page. Only a
  // draft this session owns is written over; one made elsewhere meanwhile
  // (History's Restore, a phone) is left for the reader. Edits undone back to
  // the saved page drop the draft.
  const snapshotKey = snapshot ? draftContentKey(snapshot) : "";
  const draftKey = hubDraft ? draftContentKey(hubDraft.content) : null;
  const ownsDraft = !hubDraft || ownedDraftRevisions.has(hubDraft.revision);
  const autosaveBlocked = !restoreChecked || !draft.isSuccess || draftConflict || saveDraft.isPending || !ownsDraft;
  useEffect(() => {
    if (autosaveBlocked || !snapshotKey) return;
    const write = builder.unsaved && draftKey !== snapshotKey;
    const drop = !builder.unsaved && hubDraft !== null;
    if (!write && !drop) return;
    const timer = setTimeout(() => {
      if (write) {
        saveDraft.mutate({});
      } else if (hubDraft) {
        void pageHistoryApi
          .discardDraft(pageId, hubDraft.revision)
          .catch(() => undefined)
          .finally(() => {
            queryClient.setQueryData(ideKeys.draft(pageId), null);
            setRestored(null);
          });
      }
    }, AUTOSAVE_MS);
    return () => clearTimeout(timer);
    // saveDraft is stable enough: its identity changes with its state, which autosaveBlocked covers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autosaveBlocked, snapshotKey, draftKey, builder.unsaved, hubDraft, pageId, queryClient]);

  // "Save & update board" saved the page itself. A draft this session wrote is
  // now behind the page and goes; any other draft is kept for History (stale).
  const lastTick = useRef(savedTick);
  useEffect(() => {
    if (savedTick === lastTick.current) return;
    lastTick.current = savedTick;
    const pending = queryClient.getQueryData<PageDraft | null>(ideKeys.draft(pageId));
    const owned = !!pending && ownedDraftRevisions.has(pending.revision);
    const after = owned ? pageHistoryApi.discardDraft(pageId, pending.revision) : Promise.resolve();
    void after
      .catch(() => undefined)
      .finally(() => {
        setRestored(null);
        void queryClient.invalidateQueries({ queryKey: ideKeys.draft(pageId) });
        invalidateHistory();
        void queryClient.invalidateQueries({ queryKey: ideKeys.sends(pageId) });
      });
  }, [savedTick, pageId, queryClient, invalidateHistory, ownedDraftRevisions]);

  return {
    builder,
    boards,
    /** The page's own display (UX-6-1): what the Timeline, Transition and copy name, and where it is checked. */
    pageBoard,
    pageBoardId,
    /** The displays that show the page (now, then scheduled): the editor previews it as the first it fits. */
    pageDisplays,
    pages: pages.data?.pages ?? [],
    collections: collections.data?.collections ?? [],
    schedules: schedules.data?.schedules ?? [],
    draft: hubDraft,
    revisions: revisions.data?.revisions ?? [],
    revisionsError: revisions.isError,
    sends: sends.data?.sends ?? [],
    sendsError: sends.isError,
    showsOn,
    editState,
    display,
    problems,
    warnings,
    validationError: validation.isError,
    saveDraft,
    draftConflict,
    dismissDraftConflict: () => setDraftConflict(false),
    discardDraft,
    invalidateHistory,
    /** D4: the draft restored into the editor when the page opened, until it is saved or discarded. */
    restoredDraft: restored,
    /** The hub draft holds exactly the editor's content ("Draft saved 7:44 AM"). */
    draftInStep,
    /** Unsaved edits that autosave leaves alone: a draft from elsewhere is waiting (History). */
    autosavePaused: builder.unsaved && !!hubDraft && !draftInStep && !ownsDraft,
    discardRestored,
    discardOwnedDraft,
  };
}

export type CreatorIdeState = ReturnType<typeof useCreatorIde>;
