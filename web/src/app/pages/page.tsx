"use client";

import { useCallback, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { PageGridSelector } from "@/components/page-grid-selector";
import { useViewTransition } from "@/hooks/use-view-transition";
import type { DeviceType } from "@/lib/api";

export default function PagesPage() {
  const { push } = useViewTransition();
  const [activeTab, setActiveTab] = useState<DeviceType>("flagship");

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
        <Card>
          <CardHeader className="pb-3 px-4 sm:px-6">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base sm:text-lg">
                Saved Pages
              </CardTitle>
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
          </CardHeader>
          <CardContent className="px-4 sm:px-6">
            <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as DeviceType)}>
              <TabsList className="mb-4">
                <TabsTrigger value="flagship">Flagship</TabsTrigger>
                <TabsTrigger value="note">Note</TabsTrigger>
              </TabsList>
              <TabsContent value="flagship">
                <PageGridSelector
                  onSelectPage={handleSelectPage}
                  showActiveIndicator={false}
                  label="SELECT FLAGSHIP PAGE TO EDIT"
                  deviceTypeFilter="flagship"
                />
              </TabsContent>
              <TabsContent value="note">
                <PageGridSelector
                  onSelectPage={handleSelectPage}
                  showActiveIndicator={false}
                  label="SELECT NOTE PAGE TO EDIT"
                  deviceTypeFilter="note"
                />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

