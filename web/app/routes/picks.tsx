import {
  Badge,
  Box,
  Button,
  Flex,
  Grid,
  Heading,
  PageHeader,
  PageLayout,
  Skeleton,
  Stack,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Text,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CircleAlert, CircleCheck, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import Link from "@/components/smart-link";
import { queryKeys, useBoardSettings } from "@/hooks/use-board";
import { useViewTransition } from "@/hooks/use-view-transition";
import { useTranslations } from "@/i18n/translations";
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
      <Flex
        direction="col"
        className="group rounded-xl border bg-card overflow-hidden shadow-sm hover:shadow-md transition-shadow"
      >
        {/* Preview — padded dark well so the full board screenshot breathes */}
        <Flex align="center" justify="center" className="relative w-full aspect-[17/8] bg-zinc-950 p-4">
          {showImage ? (
            <Box className="relative w-full h-full">
              <img
                src={pick.image!}
                alt={pick.name}
                className="object-contain drop-shadow-xl"
                onError={() => setImgError(true)}
              />
            </Box>
          ) : (
            <Flex align="center" justify="center" className="w-full h-full">
              <Box className="grid gap-1 opacity-20 w-full" style={{ gridTemplateColumns: "repeat(22, 1fr)" }}>
                {Array.from({ length: 132 }).map((_, i) => (
                  <Box key={i} className="aspect-square rounded-sm bg-white/60" />
                ))}
              </Box>
            </Flex>
          )}
        </Flex>

        {/* Card body */}
        <Stack gap="3" className="p-5 flex-1">
          <Stack gap="1.5">
            <Heading level={3}>{pick.name}</Heading>
            <Text tone="muted" className="leading-snug">
              {pick.description}
            </Text>
          </Stack>

          {/* Required plugins */}
          {pick.required_plugins.length > 0 && (
            <Flex align="center" wrap gap="1.5">
              <Text as="span" size="xs" tone="muted" weight="medium" className="uppercase tracking-wide">
                {t("requires")}
              </Text>
              {pick.required_plugins.map((plugin) => {
                const enabled = enabledPluginIds.has(plugin.id);
                return enabled ? (
                  <Flex key={plugin.id} inline align="center" gap="1" className="text-xs text-success">
                    <CircleCheck className="h-3 w-3" />
                    {plugin.name}
                  </Flex>
                ) : (
                  <Tooltip key={plugin.id}>
                    <TooltipTrigger asChild>
                      <Link
                        href="/integrations"
                        className="inline-flex items-center gap-1 text-xs text-warning hover:underline"
                      >
                        <CircleAlert className="h-3 w-3" />
                        {plugin.name}
                      </Link>
                    </TooltipTrigger>
                    <TooltipContent side="top">
                      <Text>{t("pluginNotEnabled", { name: plugin.name })}</Text>
                    </TooltipContent>
                  </Tooltip>
                );
              })}
            </Flex>
          )}

          {/* Tags + Import */}
          <Flex align="center" justify="between" gap="2" className="mt-auto pt-1">
            <Flex wrap gap="1">
              {pick.tags.map((tag) => (
                <Badge key={tag} variant="secondary" className="text-[10px] px-1.5 py-0 h-4 font-normal">
                  {tag}
                </Badge>
              ))}
            </Flex>
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
                  <Text>
                    {t("importWithMissingPlugins", { plugins: missingPlugins.map((p) => p.name).join(", ") })}
                  </Text>
                </TooltipContent>
              )}
            </Tooltip>
          </Flex>
        </Stack>
      </Flex>
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
      <Grid cols="1" lg="2" gap="8">
        {[1, 2].map((i) => (
          <Box key={i} className="rounded-xl border overflow-hidden">
            <Skeleton className="w-full aspect-[17/8]" />
            <Stack gap="2" className="p-4">
              <Skeleton className="h-4 w-1/2" />
              <Skeleton className="h-3 w-3/4" />
              <Skeleton className="h-8 w-20 self-end mt-2" />
            </Stack>
          </Box>
        ))}
      </Grid>
    );
  }

  if (filtered.length === 0) {
    return (
      <Text tone="muted" className="text-center py-16">
        {t("empty")}
      </Text>
    );
  }

  return (
    <Grid cols="1" lg="2" gap="8">
      {filtered.map((pick) => (
        <PickCard key={pick.id} pick={pick} enabledPluginIds={enabledPluginIds} />
      ))}
    </Grid>
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

      <Flex align="center" gap="2" className="mb-6 -mt-2">
        <Text as="span" size="xs" tone="muted" className="italic">
          {t("byline")}
        </Text>
      </Flex>

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
