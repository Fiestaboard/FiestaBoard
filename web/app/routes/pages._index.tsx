import {
  Box,
  Button,
  cn,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Grid,
  Input,
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
import { Plus, X } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { LibraryViewToggle } from "@/components/library-view-toggle";
import type { ViewMode } from "@/components/page-grid-selector";
import { PageCardMenu } from "@/components/pages/page-card-menu";
import { useBoardSettings, usePages } from "@/hooks/use-board";
import { queryKeys } from "@/hooks/use-board";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api } from "@/lib/api";
import { pagesCompatibleWithBoard } from "@/lib/board-dimensions";
import { PAGE_LIBRARY_SORTS, type PageLibraryQuery, type PageLibrarySort } from "@/lib/page-library-query";

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
const LIBRARY_STORAGE_KEY = "fiestaboard_pages_library_query";

function getStoredLibraryState(): PageLibraryQuery {
  try {
    const stored = JSON.parse(sessionStorage.getItem(LIBRARY_STORAGE_KEY) ?? "null");
    return {
      text: typeof stored?.text === "string" ? stored.text : "",
      sort: PAGE_LIBRARY_SORTS.includes(stored?.sort) ? stored.sort : "name-asc",
    };
  } catch {
    return { text: "", sort: "name-asc" };
  }
}

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
  const pageCount = (pagesData?.pages ?? []).filter(
    (page) => !selectedBoard || pagesCompatibleWithBoard(page, selectedBoard),
  ).length;
  const handleDisplayFilter = (value: string) => {
    setStoredFilter(value);
    try {
      sessionStorage.setItem("fiestaboard_pages_display_filter", value);
    } catch {}
  };

  const [libraryQuery, setLibraryQuery] = useState<PageLibraryQuery>(getStoredLibraryState);
  const searchInputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    try {
      sessionStorage.setItem(LIBRARY_STORAGE_KEY, JSON.stringify(libraryQuery));
    } catch {}
  }, [libraryQuery]);

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

  // The section (pages.tsx) owns the header and the flat grammar's spacing; this is the body.
  return (
    <>
      <PageToolbar
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
            <Button variant="outline" size="sm" onClick={() => setImportOpen(true)} className="h-9 px-3">
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

      {/* Figma 297:1824: the search field (240) and the Grid / List switch sit
          together on the right of the library row. The sort select is not in the
          frame; it stays on the left (DD-W145) and fills the row on a phone. */}
      <PageToolbar>
        <Flex align="center" gap="3" wrap className="justify-between">
          <Select
            value={libraryQuery.sort}
            onValueChange={(sort) => setLibraryQuery((previous) => ({ ...previous, sort: sort as PageLibrarySort }))}
          >
            <SelectTrigger aria-label={t("sortLabel")} className="h-9 w-full sm:w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="name-asc">{t("sortNameAsc")}</SelectItem>
              <SelectItem value="name-desc">{t("sortNameDesc")}</SelectItem>
              <SelectItem value="created-desc">{t("sortCreatedDesc")}</SelectItem>
              <SelectItem value="created-asc">{t("sortCreatedAsc")}</SelectItem>
              <SelectItem value="updated-desc">{t("sortUpdatedDesc")}</SelectItem>
              <SelectItem value="updated-asc">{t("sortUpdatedAsc")}</SelectItem>
            </SelectContent>
          </Select>
          <Flex align="center" gap="3" className="w-full sm:w-auto">
            <Box className="relative min-w-0 flex-1 sm:w-60 sm:flex-none">
              <Input
                ref={searchInputRef}
                type="search"
                aria-label={t("searchLabel")}
                placeholder={t("searchPlaceholder")}
                value={libraryQuery.text}
                onChange={(event) => setLibraryQuery((previous) => ({ ...previous, text: event.target.value }))}
                className={cn(
                  "h-9 w-full [&::-webkit-search-cancel-button]:appearance-none",
                  libraryQuery.text && "pr-10",
                )}
              />
              {libraryQuery.text && (
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="absolute right-0.5 top-1/2 -translate-y-1/2"
                  aria-label={t("clearSearch")}
                  onClick={() => {
                    setLibraryQuery((previous) => ({ ...previous, text: "" }));
                    searchInputRef.current?.focus();
                  }}
                >
                  <X aria-hidden="true" />
                </Button>
              )}
            </Box>
            <LibraryViewToggle value={viewMode} onValueChange={handleViewModeChange} />
          </Flex>
        </Flex>
      </PageToolbar>

      <PageSection {...anchorProps("pages.root")}>
        <PageGridSelector
          onSelectPage={handleSelectPage}
          renderPageActions={(page, card) => <PageCardMenu page={page}>{card}</PageCardMenu>}
          label={null}
          showActiveIndicator={false}
          showCollections={false}
          libraryQuery={libraryQuery}
          compatibleBoard={selectedBoard}
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
