"use client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Box,
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuShortcut,
  DropdownMenuTrigger,
  useKbdPlatform,
} from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, Copy, Ellipsis, FileText, LayoutGrid, Pause, Pencil, Play, Trash2 } from "lucide-react";
import { type KeyboardEvent, type ReactNode, useRef, useState } from "react";
import { toast } from "sonner";

import { ShowNow } from "@/components/collection-show-now";
import { useCurrentBoard } from "@/components/current-board-context";
import { ExportPageDialog } from "@/components/pages/export-page-dialog";
import { queryKeys } from "@/hooks/use-board";
import { useCoarsePointer } from "@/hooks/use-coarse-pointer";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useTranslations } from "@/i18n/translations";
import type { Page } from "@/lib/api";
import { api } from "@/lib/api";
import { pageHistoryApi } from "@/lib/api/page-history";
import { clearPreviewCacheForPage } from "@/lib/preview-cache";

/**
 * A library card with its menu (BB-B-8, BB-FP-3). On a fine pointer it is
 * Figma 299:6080: the page's name, then Edit (E) · Change Page… · Add to
 * Schedule · Duplicate (⌘D) · Export share string │ Pause <display>. On a
 * coarse pointer it is the phone's list (303:18724): no shortcut letters and
 * no Pause, and Delete page… last (on a desktop, Delete is in the editor). The ··· button
 * opens it, and so do right-click, Shift+F10 and a long-press on the card,
 * through FiestaUI's `DropdownMenu trigger="context"` (the Home board's menu),
 * which keeps the menu open when the finger lifts.
 */
export function PageCardMenu({ page, children }: { page: Pick<Page, "id" | "name">; children: ReactNode }) {
  const t = useTranslations("pages");
  const tCommon = useTranslations("common");
  const tBuilder = useTranslations("pageBuilder");
  const tTouch = useTranslations("editorTouch");
  const { push } = useViewTransition();
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const coarse = useCoarsePointer();
  const platform = useKbdPlatform();
  const tHome = useTranslations("home.contextMenu");
  const { currentBoard } = useCurrentBoard();
  const [showNowOpen, setShowNowOpen] = useState(false);
  const [shareString, setShareString] = useState<string | null>(null);

  const refreshLibrary = () => queryClient.invalidateQueries({ queryKey: queryKeys.pages, refetchType: "active" });

  const duplicate = useMutation({
    mutationFn: () => pageHistoryApi.duplicatePage(page.id, {}),
    onSuccess: (data) => {
      refreshLibrary();
      toast.success(t("toastDuplicated", { name: data.page.name }));
    },
    onError: () => toast.error(t("actionFailed")),
  });

  const exportShare = useMutation({
    mutationFn: () => api.getPageShareString(page.id),
    onSuccess: (data) => setShareString(data.share_string),
    onError: () => toast.error(tBuilder("exportFailed")),
  });

  const pause = useMutation({
    mutationFn: (paused: boolean) => api.setBoardPaused(currentBoard!.id, paused),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.boardSettings });
      queryClient.invalidateQueries({ queryKey: ["all-settings"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  const edit = () => push(`/pages/edit/${page.id}`);

  // The shortcuts the menu shows (desktop only): E edits, ⌘D / Ctrl+D
  // duplicates, from the focused card or its open menu. React bubbles the
  // portalled menu's keys here too; keys typed in this card's dialogs (the
  // Show now search) are not shortcuts.
  const onShortcut = (event: KeyboardEvent) => {
    if (coarse || event.altKey || event.shiftKey) return;
    const target = event.target as HTMLElement;
    if (!rootRef.current?.contains(target) && !target.closest("[role=menu]")) return;
    const key = event.key.toLowerCase();
    const mod = event.metaKey || event.ctrlKey;
    if (key === "e" && !mod) {
      event.preventDefault();
      edit();
    } else if (key === "d" && mod) {
      event.preventDefault();
      if (!duplicate.isPending) duplicate.mutate();
    }
  };

  const remove = useMutation({
    mutationFn: () => api.deletePage(page.id),
    onSuccess: async (data) => {
      // The card is about to go: hand focus to the next card's menu (or the
      // previous one, or the search) instead of losing it to <body>.
      const cards = Array.from(document.querySelectorAll<HTMLElement>("[data-page-card-menu]"));
      const here = rootRef.current ? cards.indexOf(rootRef.current) : -1;
      const next = cards[here + 1] ?? cards[here - 1];
      clearPreviewCacheForPage(page.id);
      // Drop the page's own query before the refetch so nothing asks for it again.
      queryClient.removeQueries({ queryKey: ["page", page.id] });
      if (data.active_page_updated) {
        queryClient.invalidateQueries({ queryKey: queryKeys.activePage(), refetchType: "active" });
        queryClient.invalidateQueries({ queryKey: queryKeys.status, refetchType: "active" });
      }
      toast.success(tBuilder("toastPageDeleted"));
      await refreshLibrary();
      (
        next?.querySelector<HTMLElement>("[data-page-card-actions]") ??
        document.querySelector<HTMLElement>('input[type="search"]')
      )?.focus();
    },
    onError: () => toast.error(t("actionFailed")),
  });

  const paused = currentBoard?.paused === true;
  const items = (
    <>
      {!coarse && (
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">{page.name}</DropdownMenuLabel>
      )}
      {/* The letters are drawn for sight; aria-keyshortcuts announces them. */}
      <DropdownMenuItem onClick={edit} aria-keyshortcuts={coarse ? undefined : "E"}>
        <Pencil aria-hidden="true" />
        {tCommon("edit")}
        {!coarse && <DropdownMenuShortcut aria-hidden="true">E</DropdownMenuShortcut>}
      </DropdownMenuItem>
      <DropdownMenuItem onClick={() => setShowNowOpen(true)}>
        <LayoutGrid aria-hidden="true" />
        {tHome("changePage")}
      </DropdownMenuItem>
      <DropdownMenuItem onClick={() => push(`/schedule?prefill_page_id=${encodeURIComponent(page.id)}`)}>
        <CalendarPlus aria-hidden="true" />
        {tTouch("addToSchedule")}
      </DropdownMenuItem>
      <DropdownMenuItem
        disabled={duplicate.isPending}
        onClick={() => duplicate.mutate()}
        aria-keyshortcuts={coarse ? undefined : platform === "apple" ? "Meta+D" : "Control+D"}
      >
        <Copy aria-hidden="true" />
        {t("duplicate")}
        {!coarse && (
          <DropdownMenuShortcut aria-hidden="true">{platform === "apple" ? "⌘D" : "Ctrl+D"}</DropdownMenuShortcut>
        )}
      </DropdownMenuItem>
      <DropdownMenuItem disabled={exportShare.isPending} onClick={() => exportShare.mutate()}>
        <FileText aria-hidden="true" />
        {t("exportShareString")}
      </DropdownMenuItem>
      {coarse ? (
        <DropdownMenuItem variant="destructive" onClick={() => setConfirmDelete(true)}>
          <Trash2 aria-hidden="true" />
          {t("deletePage")}
        </DropdownMenuItem>
      ) : (
        currentBoard && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled={pause.isPending} onClick={() => pause.mutate(!paused)}>
              {paused ? <Play aria-hidden="true" /> : <Pause aria-hidden="true" />}
              {tHome(paused ? "resume" : "pause", { board: currentBoard.name })}
            </DropdownMenuItem>
          </>
        )
      )}
    </>
  );

  return (
    <Box ref={rootRef} data-page-card-menu="" className="relative min-w-0" onKeyDown={onShortcut}>
      <DropdownMenu trigger="context">
        <DropdownMenuTrigger
          render={<Box className="min-w-0 select-none [-webkit-touch-callout:none] [&>button]:w-full" />}
        >
          {children}
        </DropdownMenuTrigger>
        <DropdownMenuContent className="min-w-56">{items}</DropdownMenuContent>
      </DropdownMenu>
      <Box className="absolute right-1.5 top-1.5">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon-touch"
              data-page-card-actions=""
              aria-label={t("cardActions", { name: page.name })}
            >
              <Ellipsis aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="min-w-56">
            {items}
          </DropdownMenuContent>
        </DropdownMenu>
      </Box>
      {showNowOpen && <ShowNow itemId={page.id} onClose={() => setShowNowOpen(false)} />}
      <ExportPageDialog shareString={shareString} onOpenChange={(open) => !open && setShareString(null)} />
      <AlertDialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{tBuilder("deletePageTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {tBuilder("deletePageConfirmation", { pageName: page.name })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tCommon("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => remove.mutate()}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {tCommon("delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Box>
  );
}
