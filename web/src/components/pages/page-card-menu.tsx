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
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, Copy, Ellipsis, Pencil, Trash2 } from "lucide-react";
import { type ReactNode, useRef, useState } from "react";
import { toast } from "sonner";

import { queryKeys } from "@/hooks/use-board";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useTranslations } from "@/i18n/translations";
import type { Page } from "@/lib/api";
import { api } from "@/lib/api";
import { pageHistoryApi } from "@/lib/api/page-history";
import { clearPreviewCacheForPage } from "@/lib/preview-cache";

/**
 * A library card with its menu (Figma 303:18724; BB-B-8): edit, add to the
 * Schedule, duplicate or delete a page without opening it. The ··· button
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

  const refreshLibrary = () => queryClient.invalidateQueries({ queryKey: queryKeys.pages, refetchType: "active" });

  const duplicate = useMutation({
    mutationFn: () => pageHistoryApi.duplicatePage(page.id, {}),
    onSuccess: (data) => {
      refreshLibrary();
      toast.success(t("toastDuplicated", { name: data.page.name }));
    },
    onError: () => toast.error(t("actionFailed")),
  });

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

  const items = (
    <>
      <DropdownMenuItem onClick={() => push(`/pages/edit/${page.id}`)}>
        <Pencil aria-hidden="true" />
        {tCommon("edit")}
      </DropdownMenuItem>
      <DropdownMenuItem onClick={() => push(`/schedule?prefill_page_id=${encodeURIComponent(page.id)}`)}>
        <CalendarPlus aria-hidden="true" />
        {tTouch("addToSchedule")}
      </DropdownMenuItem>
      <DropdownMenuItem disabled={duplicate.isPending} onClick={() => duplicate.mutate()}>
        <Copy aria-hidden="true" />
        {t("duplicate")}
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem variant="destructive" onClick={() => setConfirmDelete(true)}>
        <Trash2 aria-hidden="true" />
        {t("deletePage")}
      </DropdownMenuItem>
    </>
  );

  return (
    <Box ref={rootRef} data-page-card-menu="" className="group/card relative h-full min-w-0">
      <DropdownMenu trigger="context">
        <DropdownMenuTrigger
          render={<Box className="h-full min-w-0 select-none [-webkit-touch-callout:none] [&>button]:w-full" />}
        >
          {children}
        </DropdownMenuTrigger>
        <DropdownMenuContent className="min-w-56">{items}</DropdownMenuContent>
      </DropdownMenu>
      {/* A grid card's ··· sits beside its meta block (Figma 297:1824, 40 × 40);
          a list row's at its top right. */}
      <Box className="absolute right-1.5 top-1.5 group-has-[[data-card-meta]]/card:top-auto group-has-[[data-card-meta]]/card:bottom-4">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon-lg"
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
