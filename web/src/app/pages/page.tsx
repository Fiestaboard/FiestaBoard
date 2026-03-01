"use client";

import { useCallback, useState, useMemo, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Plus, LayoutGrid, List } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PageGridSelector } from "@/components/page-grid-selector";
import type { ViewMode } from "@/components/page-grid-selector";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useBoardSettings } from "@/hooks/use-board";
import type { DeviceType } from "@/lib/api";

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
        <div className="mb-4 sm:mb-6">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
            Pages
          </h1>
          <p className="text-muted-foreground mt-1 text-sm sm:text-base">
            Create and manage content for your board
          </p>
        </div>

        {/* Page Grid */}
        <Card className="animate-card-fade-in">
          <CardHeader className="pb-3 px-4 sm:px-6">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base sm:text-lg">
                Saved Pages
              </CardTitle>
              <div className="flex items-center gap-2">
                <div className="flex items-center border rounded-md" role="group" aria-label="View mode">
                  <Button
                    size="sm"
                    variant={viewMode === "grid" ? "secondary" : "ghost"}
                    onClick={() => handleViewModeChange("grid")}
                    className="h-8 w-8 p-0 rounded-r-none"
                    aria-label="Grid view"
                    aria-pressed={viewMode === "grid"}
                  >
                    <LayoutGrid className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant={viewMode === "list" ? "secondary" : "ghost"}
                    onClick={() => handleViewModeChange("list")}
                    className="h-8 w-8 p-0 rounded-l-none"
                    aria-label="List view"
                    aria-pressed={viewMode === "list"}
                  >
                    <List className="h-4 w-4" />
                  </Button>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleCreateNew}
                  className="h-9 sm:h-8 px-3 text-xs"
                >
                  <Plus className="h-4 w-4 sm:h-3 sm:w-3 mr-1" />
                  New
                </Button>
              </div>
            </div>
          </CardHeader>
          <CardContent className="px-4 sm:px-6">
            {hasMultipleDevices ? (
              <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as DeviceType)}>
                <TabsList className="mb-4">
                  {configuredDevices.includes("flagship") && (
                    <TabsTrigger value="flagship">Flagship</TabsTrigger>
                  )}
                  {configuredDevices.includes("note") && (
                    <TabsTrigger value="note">Note</TabsTrigger>
                  )}
                </TabsList>
                {configuredDevices.includes("flagship") && (
                  <TabsContent value="flagship">
                    <PageGridSelector
                      onSelectPage={handleSelectPage}
                      showActiveIndicator={false}
                      label="SELECT FLAGSHIP PAGE TO EDIT"
                      deviceTypeFilter="flagship"
                      viewMode={viewMode}
                      showCarousels={false}
                    />
                  </TabsContent>
                )}
                {configuredDevices.includes("note") && (
                  <TabsContent value="note">
                    <PageGridSelector
                      onSelectPage={handleSelectPage}
                      showActiveIndicator={false}
                      label="SELECT NOTE PAGE TO EDIT"
                      deviceTypeFilter="note"
                      viewMode={viewMode}
                      showCarousels={false}
                    />
                  </TabsContent>
                )}
              </Tabs>
            ) : (
              <PageGridSelector
                onSelectPage={handleSelectPage}
                showActiveIndicator={false}
                label="SELECT PAGE TO EDIT"
                deviceTypeFilter={configuredDevices[0] as DeviceType}
                viewMode={viewMode}
                showCarousels={false}
              />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
