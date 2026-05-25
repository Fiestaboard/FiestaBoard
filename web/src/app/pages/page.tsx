"use client";

import { useCallback, useState, useMemo, useEffect, useRef } from "react";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { Plus, LayoutGrid, List, FileText, Download } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import type { ViewMode } from "@/components/page-grid-selector";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useBoardSettings } from "@/hooks/use-board";
import type { DeviceType } from "@/lib/api";
import { api } from "@/lib/api";
import { useTranslations } from "next-intl";
import { PageHeader } from "@/components/page-header";
import { PageLayout } from "@/components/page-layout";
import { PageToolbar } from "@/components/page-toolbar";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/hooks/use-board";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";

// Lazy load PageGridSelector so the header renders immediately
const PageGridSelector = dynamic(
  () => import("@/components/page-grid-selector").then(mod => ({ default: mod.PageGridSelector })),
  {
    ssr: false,
    loading: () => (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="aspect-[9/16] w-full rounded-lg" />
        ))}
      </div>
    ),
  }
);

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
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t("importDialogCancel")}</Button>
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
  const configuredDevices = useMemo(() => boardSettings?.devices ?? ["flagship"], [boardSettings]);
  const hasMultipleDevices = configuredDevices.length > 1;
  const [activeTab, setActiveTab] = useState<DeviceType>("flagship");
  const [viewMode, setViewMode] = useState<ViewMode>(getStoredViewMode);
  const [importOpen, setImportOpen] = useState(false);

  useEffect(() => {
    if (!configuredDevices.includes(activeTab)) {
      setActiveTab(configuredDevices[0] as DeviceType);
    }
  }, [configuredDevices, activeTab]);

  const handleViewModeChange = useCallback((mode: ViewMode) => {
    setViewMode(mode);
    try {
      localStorage.setItem(VIEW_MODE_STORAGE_KEY, mode);
    } catch {}
  }, []);

  const handleSelectPage = useCallback((pageId: string) => {
    push(`/pages/edit/${pageId}`, { transitionType: "slide-up" });
  }, [push]);

  const handleCreateNew = useCallback(() => {
    push(`/pages/new?device=${activeTab}`, { transitionType: "slide-up" });
  }, [push, activeTab]);

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
              <Button
                variant="brand"
                size="sm"
                onClick={handleCreateNew}
                className="h-9 sm:h-8 px-3 text-xs btn-lift"
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
            </div>
          }
        />

        <div className="animate-card-fade-in" style={{ animationDelay: "150ms" }}>
            {hasMultipleDevices ? (
              <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as DeviceType)}>
                <TabsList className="mb-5">
                  {configuredDevices.includes("flagship") && (
                    <TabsTrigger value="flagship">{t("flagshipTab")}</TabsTrigger>
                  )}
                  {configuredDevices.includes("note") && (
                    <TabsTrigger value="note">{t("noteTab")}</TabsTrigger>
                  )}
                </TabsList>
                {configuredDevices.includes("flagship") && (
                  <TabsContent value="flagship">
                    <PageGridSelector
                      onSelectPage={handleSelectPage}
                      showActiveIndicator={false}
                      showCarousels={false}
                      deviceTypeFilter="flagship"
                      viewMode={viewMode}
                    />
                  </TabsContent>
                )}
                {configuredDevices.includes("note") && (
                  <TabsContent value="note">
                    <PageGridSelector
                      onSelectPage={handleSelectPage}
                      showActiveIndicator={false}
                      showCarousels={false}
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
                showCarousels={false}
                deviceTypeFilter={configuredDevices[0] as DeviceType}
                viewMode={viewMode}
              />
            )}
        </div>
      <ImportPageDialog open={importOpen} onOpenChange={setImportOpen} />
    </PageLayout>
  );
}
