"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, Sparkles } from "lucide-react";
import Link from "@/components/smart-link";
import { useTranslations } from "@/i18n/translations";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { PageLayout } from "@/components/page-layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { queryKeys, useBoardSettings } from "@/hooks/use-board";
import { useViewTransition } from "@/hooks/use-view-transition";
import { api, type DeviceType, type StaffPick } from "@/lib/api";

// ---------------------------------------------------------------------------
// Pick card
// ---------------------------------------------------------------------------

function PickCard({ pick, enabledPluginIds }: { pick: StaffPick; enabledPluginIds: Set<string> }) {
  const t = useTranslations("picks");
  const { push } = useViewTransition();
  const queryClient = useQueryClient();
  const [imgError, setImgError] = useState(false);

  const missingPlugins = pick.required_plugins.filter((p) => !enabledPluginIds.has(p.id));
  const hasMissingPlugins = missingPlugins.length > 0;

  const importMutation = useMutation({
    mutationFn: async () => {
      const { share_string } = await api.getStaffPickShareString(pick.id);
      return api.importPage(share_string);
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: queryKeys.pages, refetchType: "active" });
      toast.success(t("toastImported", { name: data.page.name }));
      push(`/pages/edit/${data.page.id}`, { transitionType: "slide-up" });
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  const showImage = pick.image && !imgError;

  return (
    <TooltipProvider>
      <div className="group flex flex-col rounded-xl border bg-card overflow-hidden shadow-sm hover:shadow-md transition-shadow">
        {/* Preview — padded dark well so the full board screenshot breathes */}
        <div className="relative w-full aspect-[17/8] bg-zinc-950 flex items-center justify-center p-4">
          {showImage ? (
            <div className="relative w-full h-full">
              <img
                src={pick.image!}
                alt={pick.name}
                className="object-contain drop-shadow-xl"
                onError={() => setImgError(true)}
              />
            </div>
          ) : (
            <div className="w-full h-full flex items-center justify-center">
              <div className="grid gap-1 opacity-20 w-full" style={{ gridTemplateColumns: "repeat(22, 1fr)" }}>
                {Array.from({ length: 132 }).map((_, i) => (
                  <div key={i} className="aspect-square rounded-sm bg-white/60" />
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Card body */}
        <div className="flex flex-col gap-3 p-5 flex-1">
          <div className="flex flex-col gap-1.5">
            <h3 className="font-semibold leading-tight">{pick.name}</h3>
            <p className="text-sm text-muted-foreground leading-snug">{pick.description}</p>
          </div>

          {/* Required plugins */}
          {pick.required_plugins.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wide font-medium">
                {t("requires")}
              </span>
              {pick.required_plugins.map((plugin) => {
                const enabled = enabledPluginIds.has(plugin.id);
                return enabled ? (
                  <span
                    key={plugin.id}
                    className="inline-flex items-center gap-1 text-[10px] text-green-700 dark:text-green-400"
                  >
                    <CircleCheck className="h-3 w-3" />
                    {plugin.name}
                  </span>
                ) : (
                  <Tooltip key={plugin.id}>
                    <TooltipTrigger asChild>
                      <Link
                        href="/integrations"
                        className="inline-flex items-center gap-1 text-[10px] text-amber-600 dark:text-amber-400 hover:underline"
                      >
                        <CircleAlert className="h-3 w-3" />
                        {plugin.name}
                      </Link>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      <p>{t("pluginNotEnabled", { name: plugin.name })}</p>
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </div>
          )}

          {/* Tags + Import */}
          <div className="flex items-center justify-between gap-2 mt-auto pt-1">
            <div className="flex flex-wrap gap-1">
              {pick.tags.map((tag) => (
                <Badge key={tag} variant="secondary" className="text-[10px] px-1.5 py-0 h-4 font-normal">
                  {tag}
                </Badge>
              ))}
            </div>
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="sm"
                  variant="brand"
                  className="h-8 px-3 text-xs shrink-0 btn-lift"
                  onClick={() => importMutation.mutate()}
                  disabled={importMutation.isPending}
                >
                  {importMutation.isPending ? t("importing") : t("import")}
                </Button>
              </TooltipTrigger>
              {hasMissingPlugins && (
                <TooltipContent side="top" className="max-w-xs">
                  <p>{t("importWithMissingPlugins", { plugins: missingPlugins.map((p) => p.name).join(", ") })}</p>
                </TooltipContent>
              )}
            </Tooltip>
          </div>
        </div>
      </div>
    </TooltipProvider>
  );
}

// ---------------------------------------------------------------------------
// Grid (fetches both picks and plugin status)
// ---------------------------------------------------------------------------

function PicksGrid({ deviceType }: { deviceType: DeviceType }) {
  const t = useTranslations("picks");

  const { data: picks = [], isLoading: picksLoading } = useQuery({
    queryKey: ["staff-picks"],
    queryFn: () => api.getStaffPicks(),
    staleTime: 5 * 60 * 1000,
  });

  const { data: pluginsData } = useQuery({
    queryKey: ["plugins"],
    queryFn: () => api.listPlugins(),
    staleTime: 60 * 1000,
  });

  const enabledPluginIds = useMemo<Set<string>>(() => {
    if (!pluginsData) return new Set();
    return new Set(pluginsData.plugins.filter((p) => p.enabled).map((p) => p.id));
  }, [pluginsData]);

  const filtered = picks.filter((p) => p.device_type === deviceType);

  if (picksLoading) {
    return (
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {[1, 2].map((i) => (
          <div key={i} className="rounded-xl border overflow-hidden">
            <Skeleton className="w-full aspect-[17/8]" />
            <div className="p-4 flex flex-col gap-2">
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-3 w-3/4" />
              <Skeleton className="h-8 w-20 self-end mt-2" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (filtered.length === 0) {
    return <p className="text-sm text-muted-foreground text-center py-16">{t("empty")}</p>;
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
      {filtered.map((pick) => (
        <PickCard key={pick.id} pick={pick} enabledPluginIds={enabledPluginIds} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PicksPage() {
  const t = useTranslations("picks");
  const { data: boardSettings } = useBoardSettings();
  const configuredDevices = boardSettings?.devices ?? ["flagship"];
  const hasMultipleDevices = configuredDevices.length > 1;
  const [activeTab, setActiveTab] = useState<DeviceType>("flagship");

  return (
    <PageLayout>
      <PageHeader icon={Sparkles} title={t("title")} description={t("description")} />

      <div className="flex items-center gap-2 mb-6 -mt-2">
        <span className="text-xs text-muted-foreground italic">{t("byline")}</span>
      </div>

      {hasMultipleDevices ? (
        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as DeviceType)}>
          <TabsList className="mb-6">
            {configuredDevices.includes("flagship") && <TabsTrigger value="flagship">{t("flagshipTab")}</TabsTrigger>}
            {configuredDevices.includes("note") && <TabsTrigger value="note">{t("noteTab")}</TabsTrigger>}
          </TabsList>
          {configuredDevices.includes("flagship") && (
            <TabsContent value="flagship">
              <PicksGrid deviceType="flagship" />
            </TabsContent>
          )}
          {configuredDevices.includes("note") && (
            <TabsContent value="note">
              <PicksGrid deviceType="note" />
            </TabsContent>
          )}
        </Tabs>
      ) : (
        <PicksGrid deviceType={configuredDevices[0] as DeviceType} />
      )}
    </PageLayout>
  );
}
