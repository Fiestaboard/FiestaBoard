import {
  Box,
  Button,
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
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Text,
  Textarea,
} from "@fiestaboard/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, LayoutGrid, List, Plus } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { useCurrentBoard } from "@/components/current-board-context";
import type { ViewMode } from "@/components/page-grid-selector";
import { useBoardSettings, usePages } from "@/hooks/use-board";
import { queryKeys } from "@/hooks/use-board";
import { useDepsChanged } from "@/hooks/use-deps-changed";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import type { DeviceType } from "@/lib/api";
import { api } from "@/lib/api";
import { PAGE_LIBRARY_SORTS, type PageLibraryQuery, type PageLibrarySort } from "@/lib/page-library-query";

// "panel" last: FiestaPanel pages (fit per character to a TV) get their own
// tab rather than hiding among note arrays they are not compatible with.
const DEVICE_ORDER: DeviceType[] = ["flagship", "note", "note_array", "panel"];

// Lazy load PageGridSelector so the header renders immediately
const PageGridSelectorLazy = lazy(() =>
  import("@/components/page-grid-selector").then((mod) => ({ default: mod.PageGridSelector })),
);
function PageGridSelector(props: React.ComponentProps<typeof PageGridSelectorLazy>) {
  return (
    <Suspense
      fallback={
        <Grid cols="2" sm="3" lg="4" gap="4" className="xl:grid-cols-5">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[9/16] w-full rounded-lg" />
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

function getStoredLibraryState(): PageLibraryQuery & { device: DeviceType | null } {
  try {
    const stored = JSON.parse(sessionStorage.getItem(LIBRARY_STORAGE_KEY) ?? "null");
    return {
      text: typeof stored?.text === "string" ? stored.text : "",
      sort: PAGE_LIBRARY_SORTS.includes(stored?.sort) ? stored.sort : "name-asc",
      device: DEVICE_ORDER.includes(stored?.device) ? stored.device : null,
    };
  } catch {
    return { text: "", sort: "name-asc", device: null };
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
  const { currentBoard } = useCurrentBoard();
  const configuredDevices = useMemo<DeviceType[]>(() => boardSettings?.devices ?? ["flagship"], [boardSettings]);
  // Surface pages whose device_type isn't in the user's configured boards
  // (e.g. flagship demo pages on a note-only setup) so they can still be
  // edited or deleted. See issue #943.
  const availableDevices = useMemo<DeviceType[]>(() => {
    const present = new Set<DeviceType>(configuredDevices);
    for (const page of pagesData?.pages ?? []) {
      present.add((page.device_type as DeviceType) || "flagship");
    }
    return DEVICE_ORDER.filter((d) => present.has(d));
  }, [configuredDevices, pagesData]);
  const hasMultipleDevices = availableDevices.length > 1;
  const [storedLibrary] = useState(getStoredLibraryState);
  const [libraryQuery, setLibraryQuery] = useState<PageLibraryQuery>({
    text: storedLibrary.text,
    sort: storedLibrary.sort,
  });
  const [activeTab, setActiveTab] = useState<DeviceType | null>(storedLibrary.device);
  const [viewMode, setViewMode] = useState<ViewMode>(getStoredViewMode);
  const [importOpen, setImportOpen] = useState(false);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // Keep only an explicit choice in state. Derive the default from the
  // current board so asynchronous board settings cannot lock in a stale tab.
  const current = currentBoard?.device_type;
  const preferredTab =
    (current && availableDevices.includes(current) ? current : undefined) ??
    configuredDevices.find((device) => availableDevices.includes(device)) ??
    availableDevices[0];
  // An orphan device may exist only in saved pages. Wait for both responses
  // before discarding a stored choice that is genuinely no longer available.
  if (boardSettings !== undefined && pagesData !== undefined && activeTab && !availableDevices.includes(activeTab)) {
    setActiveTab(null);
  }

  useEffect(() => {
    try {
      sessionStorage.setItem(LIBRARY_STORAGE_KEY, JSON.stringify({ ...libraryQuery, device: activeTab }));
    } catch {}
  }, [libraryQuery, activeTab]);

  const visibleTab = activeTab && availableDevices.includes(activeTab) ? activeTab : preferredTab;

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
    const device = visibleTab ?? configuredDevices[0] ?? "flagship";
    // On the selected display's own tab, ask for no device: the editor then
    // targets that display exactly (its grid, model and character set).
    if (currentBoard && currentBoard.device_type === device) {
      push("/pages/new");
      return;
    }
    push(`/pages/new?device=${device}`);
  }, [push, visibleTab, configuredDevices, currentBoard]);

  // The section (pages.tsx) owns the card and the header; this is the body.
  return (
    <>
      <PageToolbar
        left={
          <Flex align="center" className="border rounded-md" role="group" aria-label={t("viewModeLabel")}>
            <Button
              size="sm"
              variant={viewMode === "grid" ? "secondary" : "ghost"}
              onClick={() => handleViewModeChange("grid")}
              className="h-8 w-8 p-0 rounded-r-none"
              aria-label={t("gridView")}
              aria-pressed={viewMode === "grid"}
            >
              <LayoutGrid className="h-4 w-4" />
            </Button>
            <Button
              size="sm"
              variant={viewMode === "list" ? "secondary" : "ghost"}
              onClick={() => handleViewModeChange("list")}
              className="h-8 w-8 p-0 rounded-l-none"
              aria-label={t("listView")}
              aria-pressed={viewMode === "list"}
            >
              <List className="h-4 w-4" />
            </Button>
          </Flex>
        }
        right={
          <Flex align="center" gap="2">
            <Button
              variant="brand"
              size="sm"
              onClick={handleCreateNew}
              className="h-9 sm:h-8 px-3 text-xs btn-lift"
              {...anchorProps("pages.new")}
            >
              <Plus className="h-4 w-4 sm:h-3 sm:w-3 mr-1" />
              {t("newPage")}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setImportOpen(true)}
              className="h-9 sm:h-8 px-3 text-xs btn-lift"
            >
              <Download className="h-4 w-4 sm:h-3 sm:w-3 mr-1" />
              {t("importPage")}
            </Button>
          </Flex>
        }
      />

      <PageToolbar
        left={
          <Flex gap="2" align="center" wrap className="min-w-0 w-full">
            <Input
              ref={searchInputRef}
              type="search"
              aria-label={t("searchLabel")}
              aria-describedby="page-library-search-hint"
              placeholder={t("searchPlaceholder")}
              value={libraryQuery.text}
              onChange={(event) => setLibraryQuery((previous) => ({ ...previous, text: event.target.value }))}
              className="w-full sm:w-72"
            />
            {libraryQuery.text && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setLibraryQuery((previous) => ({ ...previous, text: "" }));
                  searchInputRef.current?.focus();
                }}
              >
                {t("clearSearch")}
              </Button>
            )}
          </Flex>
        }
        right={
          <Select
            value={libraryQuery.sort}
            onValueChange={(sort) => setLibraryQuery((previous) => ({ ...previous, sort: sort as PageLibrarySort }))}
          >
            <SelectTrigger aria-label={t("sortLabel")} className="w-48">
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
        }
      />

      <PageSection {...anchorProps("pages.root")}>
        <Text id="page-library-search-hint" size="xs" tone="muted" className="mb-3">
          {t("searchHint")}
        </Text>
        {hasMultipleDevices ? (
          <Tabs value={visibleTab} onValueChange={(v) => setActiveTab(v as DeviceType)}>
            {/* No inset any more: the section's own padding puts this strip on
                the content column, and the tiles below sit on it too. */}
            <TabsList className="mb-5">
              {availableDevices.includes("flagship") && <TabsTrigger value="flagship">{t("flagshipTab")}</TabsTrigger>}
              {availableDevices.includes("note") && <TabsTrigger value="note">{t("noteTab")}</TabsTrigger>}
              {availableDevices.includes("note_array") && (
                <TabsTrigger value="note_array">{t("noteArrayTab")}</TabsTrigger>
              )}
              {availableDevices.includes("panel") && <TabsTrigger value="panel">{t("panelTab")}</TabsTrigger>}
            </TabsList>
            {availableDevices.includes("flagship") && (
              <TabsContent value="flagship">
                <PageGridSelector
                  onSelectPage={handleSelectPage}
                  label={null}
                  showActiveIndicator={false}
                  showCollections={false}
                  deviceTypeFilter="flagship"
                  viewMode={viewMode}
                  libraryQuery={libraryQuery}
                />
              </TabsContent>
            )}
            {availableDevices.includes("note") && (
              <TabsContent value="note">
                <PageGridSelector
                  onSelectPage={handleSelectPage}
                  label={null}
                  showActiveIndicator={false}
                  showCollections={false}
                  deviceTypeFilter="note"
                  viewMode={viewMode}
                  libraryQuery={libraryQuery}
                />
              </TabsContent>
            )}
            {availableDevices.includes("note_array") && (
              <TabsContent value="note_array">
                <PageGridSelector
                  onSelectPage={handleSelectPage}
                  label={null}
                  showActiveIndicator={false}
                  showCollections={false}
                  deviceTypeFilter="note_array"
                  viewMode={viewMode}
                  libraryQuery={libraryQuery}
                />
              </TabsContent>
            )}
            {availableDevices.includes("panel") && (
              <TabsContent value="panel">
                <PageGridSelector
                  onSelectPage={handleSelectPage}
                  label={null}
                  showActiveIndicator={false}
                  showCollections={false}
                  deviceTypeFilter="panel"
                  viewMode={viewMode}
                  libraryQuery={libraryQuery}
                />
              </TabsContent>
            )}
          </Tabs>
        ) : (
          <PageGridSelector
            onSelectPage={handleSelectPage}
            label={null}
            showActiveIndicator={false}
            showCollections={false}
            deviceTypeFilter={(availableDevices[0] ?? configuredDevices[0]) as DeviceType}
            viewMode={viewMode}
            libraryQuery={libraryQuery}
          />
        )}
      </PageSection>
      <ImportPageDialog open={importOpen} onOpenChange={setImportOpen} />
    </>
  );
}
