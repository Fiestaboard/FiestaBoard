import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, FileText, LayoutGrid, List, Plus } from "lucide-react";
import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import type { ViewMode } from "@/components/page-grid-selector";
import { PageHeader } from "@/components/page-header";
import { PageLayout } from "@/components/page-layout";
import { PageToolbar } from "@/components/page-toolbar";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useBoardSettings, usePages } from "@/hooks/use-board";
import { queryKeys } from "@/hooks/use-board";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useTranslations } from "@/i18n/translations";
import type { DeviceType } from "@/lib/api";
import { api } from "@/lib/api";

const DEVICE_ORDER: DeviceType[] = ["flagship", "note"];

// Lazy load PageGridSelector so the header renders immediately
const PageGridSelectorLazy = lazy(() =>
  import("@/components/page-grid-selector").then((mod) => ({ default: mod.PageGridSelector })),
);
function PageGridSelector(props: React.ComponentProps<typeof PageGridSelectorLazy>) {
  return (
    <Suspense
      fallback={
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="aspect-[9/16] w-full rounded-lg" />
          ))}
        </div>
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

  useEffect(() => {
    if (!open) setShareString("");
  }, [open]);

  const importMutation = useMutation({
    mutationFn: () => api.importPage(shareString.trim()),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pages, refetchType: "active" });
      toast.success(t("toastImported", { name: data.page.name }));
      onOpenChange(false);
      push(`/pages/edit/${data.page.id}`, { transitionType: "slide-up" });
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
        <textarea
          ref={textareaRef}
          value={shareString}
          onChange={(e) => setShareString(e.target.value)}
          placeholder={t("importDialogPlaceholder")}
          className="w-full h-28 px-3 py-2 text-xs font-mono rounded-md border bg-background resize-none focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
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
  const configuredDevices = useMemo<DeviceType[]>(
    () => boardSettings?.devices ?? ["flagship"],
    [boardSettings],
  );
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
  const [activeTab, setActiveTab] = useState<DeviceType | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>(getStoredViewMode);
  const [importOpen, setImportOpen] = useState(false);

  // Default the active tab to the user's first *configured* device once
  // settings have loaded. Pages from orphan device types (e.g. flagship
  // demo pages on a note-only setup) are still reachable via the secondary
  // tab. After the user has chosen a tab we only override if their pick
  // is no longer available.
  const settingsLoaded = boardSettings !== undefined;
  useEffect(() => {
    if (!settingsLoaded || availableDevices.length === 0) return;
    if (activeTab && availableDevices.includes(activeTab)) return;
    const preferred = configuredDevices.find((d) => availableDevices.includes(d));
    setActiveTab(preferred ?? availableDevices[0]);
  }, [settingsLoaded, availableDevices, configuredDevices, activeTab]);

  const handleViewModeChange = useCallback((mode: ViewMode) => {
    setViewMode(mode);
    try {
      localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode);
    } catch {}
  }, []);

  const handleSelectPage = useCallback(
    (pageId: string) => {
      push(`/pages/edit/${pageId}`, { transitionType: "slide-up" });
    },
    [push],
  );

  const handleCreateNew = useCallback(() => {
    const device = activeTab ?? configuredDevices[0] ?? "flagship";
    push(`/pages/new?device=${device}`, { transitionType: "slide-up" });
  }, [push, activeTab, configuredDevices]);

  return (
    <PageLayout>
      <PageHeader icon={FileText} title={t("title")} description={t("description")} />
      <PageToolbar
        left={
          <div className="flex items-center border rounded-md" role="group" aria-label={t("viewModeLabel")}>
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
          </div>
        }
        right={
          <div className="flex items-center gap-2">
            <Button variant="brand" size="sm" onClick={handleCreateNew} className="h-9 sm:h-8 px-3 text-xs btn-lift">
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
          </div>
        }
      />

      <div className="animate-card-fade-in" style={{ animationDelay: "150ms" }}>
        {hasMultipleDevices ? (
          <Tabs value={activeTab ?? availableDevices[0]} onValueChange={(v) => setActiveTab(v as DeviceType)}>
            <TabsList className="mb-5">
              {availableDevices.includes("flagship") && <TabsTrigger value="flagship">{t("flagshipTab")}</TabsTrigger>}
              {availableDevices.includes("note") && <TabsTrigger value="note">{t("noteTab")}</TabsTrigger>}
            </TabsList>
            {availableDevices.includes("flagship") && (
              <TabsContent value="flagship">
                <PageGridSelector
                  onSelectPage={handleSelectPage}
                  showActiveIndicator={false}
                  showCollections={false}
                  deviceTypeFilter="flagship"
                  viewMode={viewMode}
                />
              </TabsContent>
            )}
            {availableDevices.includes("note") && (
              <TabsContent value="note">
                <PageGridSelector
                  onSelectPage={handleSelectPage}
                  showActiveIndicator={false}
                  showCollections={false}
                  deviceTypeFilter="note"
                  viewMode={viewMode}
                />
              </TabsContent>
            )}
          </Tabs>
        ) : (
          <PageGridSelector
            onSelectPage={handleSelectPage}
            showActiveIndicator={false}
            showCollections={false}
            deviceTypeFilter={(availableDevices[0] ?? configuredDevices[0]) as DeviceType}
            viewMode={viewMode}
          />
        )}
      </div>
      <ImportPageDialog open={importOpen} onOpenChange={setImportOpen} />
    </PageLayout>
  );
}
