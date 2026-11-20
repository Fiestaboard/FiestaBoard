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
  Button,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CalendarPlus, Copy, Ellipsis, Pencil, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { queryKeys } from "@/hooks/use-board";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useTranslations } from "@/i18n/translations";
import type { Page } from "@/lib/api";
import { api } from "@/lib/api";
import { pageHistoryApi } from "@/lib/api/page-history";
import { clearPreviewCacheForPage } from "@/lib/preview-cache";

/**
 * A library card's ··· menu (Figma 303:18724; BB-B-8): edit, add to the
 * Schedule, duplicate or delete a page without opening it. Opened by the
 * button, by a right-click or a long-press on the card (`open`/`onOpenChange`).
 */
export function PageCardMenu({
  page,
  open,
  onOpenChange,
}: {
  page: Pick<Page, "id" | "name">;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const t = useTranslations("pages");
  const tCommon = useTranslations("common");
  const tBuilder = useTranslations("pageBuilder");
  const tTouch = useTranslations("editorTouch");
  const { push } = useViewTransition();
  const queryClient = useQueryClient();
  const [confirmDelete, setConfirmDelete] = useState(false);

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
    onSuccess: (data) => {
      clearPreviewCacheForPage(page.id);
      // Drop the page's own query before the refetch so nothing asks for it again.
      queryClient.removeQueries({ queryKey: ["page", page.id] });
      refreshLibrary();
      if (data.active_page_updated) {
        queryClient.invalidateQueries({ queryKey: queryKeys.activePage(), refetchType: "active" });
        queryClient.invalidateQueries({ queryKey: queryKeys.status, refetchType: "active" });
      }
      toast.success(tBuilder("toastPageDeleted"));
    },
    onError: () => toast.error(t("actionFailed")),
  });

  return (
    <>
      <DropdownMenu open={open} onOpenChange={onOpenChange}>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-touch" aria-label={t("cardActions", { name: page.name })}>
            <Ellipsis aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
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
        </DropdownMenuContent>
      </DropdownMenu>
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
              {remove.isPending ? tCommon("deleting") : tCommon("delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
