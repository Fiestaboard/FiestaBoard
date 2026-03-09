"use client";

import { useCallback, useState, useMemo, useEffect } from "react";
import dynamic from "next/dynamic";
import { Button } from "@/components/ui/button";
import { Plus, LayoutGrid, List, FileText } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import type { ViewMode } from "@/components/page-grid-selector";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useBoardSettings } from "@/hooks/use-board";
import type { DeviceType } from "@/lib/api";
import { useTranslations } from "next-intl";

// Lazy load PageGridSelector so the header renders immediately
const PageGridSelector = dynamic(
  () => import("@/components/page-grid-selector").then(mod => ({ default: mod.PageGridSelector })),
  {
    ssr: false,
    loading: () => (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-3 sm:gap-4">
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

export default function PagesPage() {
  const { push } = useViewTransition();
  const t = useTranslations("pages");
  const { data: boardSettings } = useBoardSettings();
  const configuredDevices = useMemo(() => boardSettings?.devices ?? ["flagship"], [boardSettings]);
  const hasMultipleDevices = configuredDevices.length > 1;
  const [activeTab, setActiveTab] = useState<DeviceType>("flagship");
  const [viewMode, setViewMode] = useState<ViewMode>(getStoredViewMode);

  // Sync activeTab when configured devices change
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
    <div className="min-h-screen bg-background overflow-x-hidden">
      <div className="container mx-auto px-3 sm:px-4 md:px-6 py-4 sm:py-6 md:py-8 max-w-full">
        <div className="mb-6 animate-card-fade-in" style={{ animationDelay: "0ms" }}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="page-title flex items-center gap-3">
                <FileText className="h-7 w-7 text-brand-emphasis" />
                {t("title")}
              </h1>
              <p className="page-description">
                {t("description")}
              </p>
            </div>
            <div className="flex items-center gap-3 pt-1">
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
              <Button
                variant="brand"
                size="sm"
                onClick={handleCreateNew}
                className="h-9 sm:h-8 px-3 text-xs btn-lift"
              >
                <Plus className="h-4 w-4 sm:h-3 sm:w-3 mr-1" />
                {t("newPage")}
              </Button>
            </div>
          </div>
        </div>

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
                deviceTypeFilter={configuredDevices[0] as DeviceType}
                viewMode={viewMode}
              />
            )}
        </div>
      </div>
    </div>
  );
}
