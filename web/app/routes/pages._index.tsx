import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Grid,
  PageSection,
  PageToolbar,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Text,
  Textarea,
} from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, LayoutGrid, List, Plus } from "lucide-react";
import { lazy, Suspense, useCallback, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import type { ViewMode } from "@/components/page-grid-selector";
import { useBoardSettings, usePages } from "@/hooks/use-board";
import { queryKeys } from "@/hooks/use-board";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api } from "@/lib/api";
import { pagesCompatibleWithBoard } from "@/lib/board-dimensions";

// Lazy load PageGridSelector so the header renders immediately
const PageGridSelectorLazy = lazy(() =>
  import("@/components/page-grid-selector").then((mod) => ({ default: mod.PageGridSelector })),
);
function PageGridSelector(props: React.ComponentProps<typeof PageGridSelectorLazy>) {
  return (
    <Suspense
      fallback={
        <Grid cols="1" sm="2" gap="4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-52 w-full rounded-xl" />
          ))}
        </Grid>
      }
    >
      <PageGridSelectorLazy {...props} />
    </Suspense>
  );
}

const VIEW_MODE_STORAGE_KEY = "fiestaboard_pages_view_mode";

function getStoredViewMode(): ViewMode {
  if (typeof window === "undefined") return "grid";
  try {
    const stored = localStorage.getItem(VIEW_MODE_STORAGE_KEY);
    if (stored === "grid" || stored === "list") return stored;
  } catch {}
  return "grid";
}

export function ImportPageDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  const t = useTranslations("pages");
  const { push } = useViewTransition();
  const queryClient = useQueryClient();
  const [shareString, setShareString] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Clear the pasted share string when the dialog closes. Done during render
  // so a reopen can never flash the previous paste
  // (react-hooks/set-state-in-effect, issue #1568).
  if (useDepsChanged([open]) && !open) {
    setShareString("");
  }

  const importMutation = useMutation({
    mutationFn: () => api.importPage(shareString.trim()),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pages, refetchType: "active" });
      toast.success(t("toastImported", { name: data.name }));
      onOpenChange(false);
      push(`/pages/edit/${data.id}`);
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t("importDialogTitle")}</DialogTitle>
          <DialogDescription>{t("importDialogDescription")}</DialogDescription>
        </DialogHeader>
        <Textarea
          ref={textareaRef}
          value={shareString}
          onChange={(e) => setShareString(e.target.value)}
          placeholder={t("importDialogPlaceholder")}
          className="h-28 text-xs font-mono resize-none"
          spellCheck={false}
          autoFocus
        />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("importDialogCancel")}
          </Button>
          <Button
            variant="secondary"
            onClick={() => importMutation.mutate()}
            disabled={!shareString.trim() || importMutation.isPending}
          >
            {importMutation.isPending ? t("importDialogImporting") : t("importDialogImport")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function PagesPage() {
  const { push } = useViewTransition();
  const t = useTranslations("pages");
  const { data: boardSettings } = useBoardSettings();
  const { data: pagesData } = usePages();
  const boards = useMemo(() => boardSettings?.boards ?? [], [boardSettings?.boards]);
  const [storedFilter, setStoredFilter] = useState(() => {
    try {
      return sessionStorage.getItem("fiestaboard_pages_display_filter") ?? "all";
    } catch {
      return "all";
    }
  });
  const selectedBoard = boards.find((board) => board.id === storedFilter);
  const displayFilter = selectedBoard?.id ?? "all";
  const [viewMode, setViewMode] = useState<ViewMode>(getStoredViewMode);
  const [importOpen, setImportOpen] = useState(false);
  // The pages the chosen display shows. Pages it can't show are still listed
  // (flagged) but are not counted.
  const pageCount = (pagesData?.pages ?? []).filter(
    (page) => !selectedBoard || pagesCompatibleWithBoard(page, selectedBoard),
  ).length;
  const handleDisplayFilter = (value: string) => {
    setStoredFilter(value);
    try {
      sessionStorage.setItem("fiestaboard_pages_display_filter", value);
    } catch {}
  };

  const handleViewModeChange = useCallback((mode: ViewMode) => {
    setViewMode(mode);
    try {
      localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode);
    } catch {}
  }, []);

  const handleSelectPage = useCallback(
    (pageId: string) => {
      push(`/pages/edit/${pageId}`);
    },
    [push],
  );

  const handleCreateNew = useCallback(() => {
    // The editor uses the active display's exact grid/model. Selecting a
    // different library filter only changes browsing, not the sidebar display.
    push(selectedBoard ? `/pages/new?board=${encodeURIComponent(selectedBoard.id)}` : "/pages/new");
  }, [push, selectedBoard]);

  // The section (pages.tsx) owns the card and the header; this is the body.
  return (
    <>
      <PageToolbar
        className="!py-4 px-4 sm:px-6"
        left={
          <Flex align="center" gap="3" wrap>
            <Select value={displayFilter} onValueChange={handleDisplayFilter}>
              <SelectTrigger className="h-9 w-48" aria-label={t("displayFilter")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("allPages")}</SelectItem>
                {boards.map((board) => (
                  <SelectItem key={board.id} value={board.id}>
                    {board.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Text size="xs" tone="muted">
              {t("libraryCount", { count: pageCount })}
            </Text>
          </Flex>
        }
        right={
          <Flex align="center" gap="2" wrap>
            <Flex align="center" className="rounded-md bg-muted/50 p-0.5" role="group" aria-label={t("viewModeLabel")}>
              <Button
                size="sm"
                variant={viewMode === "grid" ? "secondary" : "ghost"}
                onClick={() => handleViewModeChange("grid")}
                className="h-8 w-8 p-0"
                aria-label={t("gridView")}
                aria-pressed={viewMode === "grid"}
              >
                <LayoutGrid className="h-4 w-4" />
              </Button>
              <Button
                size="sm"
                variant={viewMode === "list" ? "secondary" : "ghost"}
                onClick={() => handleViewModeChange("list")}
                className="h-8 w-8 p-0"
                aria-label={t("listView")}
                aria-pressed={viewMode === "list"}
              >
                <List className="h-4 w-4" />
              </Button>
            </Flex>
            <Button variant="ghost" size="sm" onClick={() => setImportOpen(true)} className="h-9 px-3">
              <Download className="h-4 w-4 mr-1" />
              {t("importPage")}
            </Button>
            <Button
              variant="brand"
              size="sm"
              onClick={handleCreateNew}
              className="h-9 px-3"
              {...anchorProps("pages.new")}
            >
              <Plus className="h-4 w-4 mr-1" />
              {t("newPage")}
            </Button>
          </Flex>
        }
      />

      <PageSection className="px-4 pt-0 pb-4 sm:px-6 [&:not(:first-child)]:border-t-0" {...anchorProps("pages.root")}>
        <PageGridSelector
          onSelectPage={handleSelectPage}
          label={null}
          showActiveIndicator={false}
          showCollections={false}
          compatibleBoard={selectedBoard}
          misfitsSelectable
          viewMode={viewMode}
        />
        {selectedBoard && pagesData && pageCount === 0 && (
          <Button variant="outline" size="sm" className="mt-3" onClick={() => handleDisplayFilter("all")}>
            {t("clearFilter")}
          </Button>
        )}
      </PageSection>
      <ImportPageDialog open={importOpen} onOpenChange={setImportOpen} />
    </>
  );
}
