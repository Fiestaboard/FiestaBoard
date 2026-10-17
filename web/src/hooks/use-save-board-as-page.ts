"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { toast } from "sonner";

import { queryKeys } from "@/hooks/use-board";
import { useRouter } from "@/hooks/use-router";
import { useLocale, useTranslations } from "@/i18n/translations";
import { api, type Page } from "@/lib/api";
import { type BoardGeometry, buildBoardPageCreate } from "@/lib/board-characters-to-template";

/**
 * Save a board grid as a new template page (issue #1945) — the one path both
 * faces of the out-of-sync banner use, on Home and on a display's own page.
 *
 * The page is auto-named in the APP's locale ("Saved from board Oct 17, 2026,
 * 11:42 PM" / "Vom Board gespeichert 17.10.2026, 23:42"); renaming is one tap
 * away through the toast's Open action. A failure is toasted and rethrown so
 * the caller keeps its Save button.
 */
export function useSaveBoardAsPage(): {
  save: (grid: number[][], geometry: BoardGeometry) => Promise<Page>;
  isPending: boolean;
} {
  const t = useTranslations("boardOutOfSync");
  const locale = useLocale();
  const router = useRouter();
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: ({ grid, geometry }: { grid: number[][]; geometry: BoardGeometry }) => {
      const date = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(new Date());
      return api.createPage(buildBoardPageCreate(grid, geometry, t("externalPageName", { date })));
    },
  });
  const { mutateAsync } = mutation;

  const save = useCallback(
    async (grid: number[][], geometry: BoardGeometry): Promise<Page> => {
      let page: Page;
      try {
        page = await mutateAsync({ grid, geometry });
      } catch (error) {
        toast.error(t("toastSaveFailed"));
        throw error;
      }
      queryClient.invalidateQueries({ queryKey: queryKeys.pages });
      toast.success(t("toastSaved", { pageName: page.name }), {
        action: { label: t("toastOpen"), onClick: () => router.push(`/pages/edit/${page.id}`) },
      });
      return page;
    },
    [mutateAsync, queryClient, router, t],
  );

  return { save, isPending: mutation.isPending };
}
