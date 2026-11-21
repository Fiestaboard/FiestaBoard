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
import { showsOnModel } from "@/lib/ide/shows-on";

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

interface BuilderState {
  unsaved: boolean;
  mirroring: boolean;
  snapshot: CurrentPageSnapshot | null;
}

/** The content a draft and the editor are compared on. */
export function contentKey(content: Pick<PageContent, "name" | "template" | "line_metadata"> | null | undefined) {
  if (!content) return "";
  return JSON.stringify([content.name, content.template ?? [], content.line_metadata ?? []]);
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
  const { boards, currentBoardId, currentBoard } = useCurrentBoard();
  const [builder, setBuilder] = useState<BuilderState>({ unsaved: false, mirroring: false, snapshot: null });

  useEffect(() => {
    const read = () => {
      const handle = builderRef.current;
      if (!handle) return;
      const next: BuilderState = {
        unsaved: handle.hasUnsavedChanges(),
        mirroring: handle.isMirroring(),
        snapshot: handle.getCurrentPage() ?? null,
      };
      setBuilder((previous) =>
        previous.unsaved === next.unsaved &&
        previous.mirroring === next.mirroring &&
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
  const activeAnswers = useQueries({
    queries: boards.map((board) => ({
      queryKey: ideKeys.active(board.id),
      queryFn: () => api.getActiveSchedule(board.id),
      refetchInterval: HUB_REFRESH_MS,
      retry: false,
    })),
    combine: (results) => results.map((result) => result.data),
  });

  const snapshot = builder.snapshot;
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
            ...(currentBoardId && { board_id: currentBoardId }),
          }
        : null,
    [snapshot, currentBoardId],
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
    enabled: !!targetKey && !!currentBoardId,
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

  const hubDraft: PageDraft | null = draft.data ?? null;
  const unsavedBeyondDraft =
    builder.unsaved && (!hubDraft || contentKey(hubDraft.content) !== contentKey(snapshot ?? undefined));
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
  const ownedDraftRevisions = useRef(new Set<string>());
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
      ownedDraftRevisions.current.add(saved.revision);
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
  const publishDraft = useMutation({
    mutationFn: () =>
      pageHistoryApi.publishDraft(pageId, hubDraft ? { expected_draft_revision: hubDraft.revision } : {}),
    onSuccess: async () => {
      queryClient.setQueryData(ideKeys.draft(pageId), null);
      invalidateHistory();
      await builderRef.current?.reloadFromServer();
    },
  });

  // "Save & update board" saved the page itself. A draft this session wrote is
  // now behind the page and goes; any other draft is kept for History (stale).
  const lastTick = useRef(savedTick);
  useEffect(() => {
    if (savedTick === lastTick.current) return;
    lastTick.current = savedTick;
    const pending = queryClient.getQueryData<PageDraft | null>(ideKeys.draft(pageId));
    const owned = !!pending && ownedDraftRevisions.current.has(pending.revision);
    const after = owned ? pageHistoryApi.discardDraft(pageId, pending.revision) : Promise.resolve();
    void after
      .catch(() => undefined)
      .finally(() => {
        void queryClient.invalidateQueries({ queryKey: ideKeys.draft(pageId) });
        invalidateHistory();
        void queryClient.invalidateQueries({ queryKey: ideKeys.sends(pageId) });
      });
  }, [savedTick, pageId, queryClient, invalidateHistory]);

  return {
    builder,
    boards,
    currentBoard,
    currentBoardId,
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
    publishDraft,
    invalidateHistory,
  };
}

export type CreatorIdeState = ReturnType<typeof useCreatorIde>;
