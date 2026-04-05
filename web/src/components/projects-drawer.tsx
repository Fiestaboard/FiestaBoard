"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { GalleryHorizontalEnd, Search, Clock, FileText } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import { ViewTransitionLink } from "@/components/view-transition-link";
import { api } from "@/lib/api";
import { queryKeys } from "@/hooks/use-board";
import { useSidebar } from "@/components/sidebar-context";
import { useTranslations } from "next-intl";

function formatInterval(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}

export function ProjectsDrawer() {
  const { projectsDrawerOpen, setProjectsDrawerOpen } = useSidebar();
  const [search, setSearch] = useState("");
  const t = useTranslations("projectsDrawer");

  const { data: carouselsData, isLoading } = useQuery({
    queryKey: queryKeys.carousels,
    queryFn: api.getCarousels,
    enabled: projectsDrawerOpen,
  });

  const { data: pagesData } = useQuery({
    queryKey: queryKeys.pages,
    queryFn: api.getPages,
    enabled: projectsDrawerOpen,
  });

  const carousels = carouselsData?.carousels || [];
  const pages = pagesData?.pages || [];

  const filtered = useMemo(() => {
    if (!search.trim()) return carousels;
    const q = search.toLowerCase();
    return carousels.filter((c) => c.name.toLowerCase().includes(q));
  }, [carousels, search]);

  const getPageName = (pageId: string) =>
    pages.find((p) => p.id === pageId)?.name || pageId.slice(0, 8);

  return (
    <Sheet open={projectsDrawerOpen} onOpenChange={setProjectsDrawerOpen}>
      <SheetContent className="w-full sm:max-w-md overflow-y-auto" side="right">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <GalleryHorizontalEnd className="h-5 w-5" />
            {t("title")}
          </SheetTitle>
          <SheetDescription>{t("description")}</SheetDescription>
        </SheetHeader>

        <div className="mt-4 space-y-4">
          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder={t("searchPlaceholder")}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="pl-9"
            />
          </div>

          {/* Project list */}
          {isLoading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-20 w-full rounded-lg" />
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-8 text-center">
              <GalleryHorizontalEnd className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
              <p className="text-sm text-muted-foreground">
                {search.trim() ? t("noResults") : t("noProjects")}
              </p>
              <Button
                variant="brand"
                size="sm"
                className="mt-3"
                asChild
              >
                <ViewTransitionLink
                  href="/carousels"
                  onClick={() => setProjectsDrawerOpen(false)}
                >
                  {t("manageProjects")}
                </ViewTransitionLink>
              </Button>
            </div>
          ) : (
            <div className="space-y-2">
              {filtered.map((carousel) => (
                <div
                  key={carousel.id}
                  className="rounded-lg border p-3 hover:bg-accent/50 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium truncate">
                        {carousel.name}
                      </p>
                      <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
                        <FileText className="h-3 w-3" />
                        <span>
                          {carousel.page_ids.length}{" "}
                          {carousel.page_ids.length === 1 ? t("page") : t("pages")}
                        </span>
                        <Clock className="h-3 w-3 ml-1" />
                        <span>{formatInterval(carousel.interval_seconds)}</span>
                      </div>
                    </div>
                  </div>
                  {carousel.page_ids.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {carousel.page_ids.slice(0, 4).map((pid, i) => (
                        <Badge key={pid} variant="secondary" className="text-xs">
                          <span className="text-muted-foreground mr-1">{i + 1}.</span>
                          {getPageName(pid)}
                        </Badge>
                      ))}
                      {carousel.page_ids.length > 4 && (
                        <Badge variant="outline" className="text-xs">
                          +{carousel.page_ids.length - 4}
                        </Badge>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {/* Link to full page */}
          {filtered.length > 0 && (
            <div className="pt-2 border-t">
              <Button
                variant="outline"
                size="sm"
                className="w-full"
                asChild
              >
                <ViewTransitionLink
                  href="/carousels"
                  onClick={() => setProjectsDrawerOpen(false)}
                >
                  {t("manageProjects")}
                </ViewTransitionLink>
              </Button>
            </div>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
