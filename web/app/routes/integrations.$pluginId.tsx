import {
  BoardShowcase,
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Input,
  Label,
  PageSection,
  Skeleton,
  Stack,
  Text,
} from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownToLine, CopyPlus, ExternalLink } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { IntegrationReadme } from "@/components/integrations/integration-readme";
import { findOAuthConnection, OAUTH_CONNECTIONS_QUERY_KEY } from "@/components/plugin-settings";
import { SectionAction } from "@/components/section-shell";
import { useEffectiveBoardColor } from "@/hooks/use-effective-board-color";
import { useEffectiveCode62Glyph } from "@/hooks/use-effective-code62-glyph";
import { useParams, useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { anchorProps } from "@/lib/ai-choreography/anchors";
import { api } from "@/lib/api";
import { type PluginInfo } from "@/lib/api";

import { InstalledPluginRow, useInstalledPluginActions } from "./integrations._index";

function MarketplacePluginDetail() {
  const t = useTranslations("pluginDetail");
  const tCommon = useTranslations("common");
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const boardColor = useEffectiveBoardColor();
  const code62Glyph = useEffectiveCode62Glyph();
  const pluginId = params.pluginId as string;
  const [addInstanceOpen, setAddInstanceOpen] = useState(false);
  const [instanceLabel, setInstanceLabel] = useState("");
  const [isCreatingInstance, setIsCreatingInstance] = useState(false);

  // Find the registry entry for this plugin
  const { data: registryData, isLoading: isLoadingRegistry } = useQuery({
    queryKey: ["plugin-registry"],
    queryFn: api.listRegistryPlugins,
    staleTime: 5 * 60 * 1000,
  });

  const entry = registryData?.entries.find((e) => e.id === pluginId);
  const repoUrl = entry?.repository ?? "";

  const previews = entry?.previews ?? [];

  // Install mutation
  const installMutation = useMutation({
    mutationFn: async () => {
      await api.installRegistryPlugin(pluginId);
      await api.enablePlugin(pluginId);
    },
    onSuccess: () => {
      toast.success(t("toastInstalled", { name: entry?.name ?? pluginId }));
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
      queryClient.invalidateQueries({ queryKey: ["template-variables"] });
      queryClient.invalidateQueries({ queryKey: ["plugin-displays-batch"] });
      queryClient.invalidateQueries({ queryKey: ["pagePreview"] });
      router.push("/integrations?tab=installed");
    },
    onError: (err) => {
      toast.error(t("toastInstallFailed", { error: err instanceof Error ? err.message : tCommon("unknownError") }));
    },
  });

  const isInstalled = registryData?.entries.find((e) => e.id === pluginId)?.installed;
  const isLoading = isLoadingRegistry;

  async function handleAddInstance() {
    if (!instanceLabel.trim()) return;
    setIsCreatingInstance(true);
    try {
      await api.createPluginInstance(pluginId, instanceLabel.trim());
      toast.success(t("toastInstanceCreated", { label: instanceLabel }));
      queryClient.invalidateQueries({ queryKey: ["plugins"] });
      setAddInstanceOpen(false);
      setInstanceLabel("");
    } catch (err) {
      toast.error(
        t("toastCreateInstanceFailed", { error: err instanceof Error ? err.message : tCommon("unknownError") }),
      );
    } finally {
      setIsCreatingInstance(false);
    }
  }

  return (
    <>
      {/* The Integrations section (integrations.tsx) names the plugin in the
          breadcrumb and heading above this; its actions sit on that row. */}
      <SectionAction>
        <Flex align="center" gap="2" wrap>
          {entry?.repository && (
            <Button variant="outline" size="sm" asChild>
              {/* asChild hands this anchor Button's own chrome (border/bg/text) — TextLink's
                  underline+text-primary styling would clash with that, so it stays raw
                  (couldn't snap — see wave 1 report). */}
              {/* eslint-disable-next-line react/forbid-elements -- single Slot child of Button asChild; the Button merges its chrome onto this anchor and TextLink would layer conflicting link styling */}
              <a href={entry.repository} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                {t("githubLink")}
              </a>
            </Button>
          )}
          {!isLoading &&
            (isInstalled ? (
              <Button size="sm" variant="outline" onClick={() => setAddInstanceOpen(true)}>
                <CopyPlus className="h-3.5 w-3.5 mr-1.5" />
                {t("addInstance")}
              </Button>
            ) : (
              <Button size="sm" onClick={() => installMutation.mutate()} disabled={installMutation.isPending}>
                {installMutation.isPending ? (
                  <Spinner label={null} className="h-3.5 w-3.5 mr-1.5" />
                ) : (
                  <ArrowDownToLine className="h-3.5 w-3.5 mr-1.5" aria-hidden="true" />
                )}
                {installMutation.isPending ? t("installing") : t("install")}
              </Button>
            ))}
        </Flex>
      </SectionAction>

      <Box {...anchorProps(`plugin.${pluginId}`)}>
        {/* Board hero — what this plugin actually puts on a board, the same
            way the public directory leads at fiestaboard.app/plugins. Absent
            for plugins that predate the previews contract. */}
        {previews.length > 0 && (
          <PageSection>
            <BoardShowcase
              previews={previews}
              previewLabel={t("boardPreviewLabel", { name: entry?.name ?? pluginId })}
              defaultBoardType={boardColor}
              code62Glyph={code62Glyph}
              labels={{
                flagship: t("deviceFlagship"),
                note: t("deviceNote"),
                noteArray: t("deviceNoteArray"),
                boardShape: t("boardShapeLabel"),
                boardColor: t("boardColorLabel"),
                blackBoard: t("blackBoard"),
                whiteBoard: t("whiteBoard"),
              }}
            />
          </PageSection>
        )}

        <PageSection>
          <IntegrationReadme
            pluginId={pluginId}
            repository={entry?.repository}
            branch={entry?.branch}
            author={entry?.author}
          />
        </PageSection>
      </Box>

      <Dialog open={addInstanceOpen} onOpenChange={setAddInstanceOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("addInstanceOfTitle", { name: entry?.name ?? pluginId })}</DialogTitle>
            <DialogDescription>{t("addInstanceDescription")}</DialogDescription>
          </DialogHeader>
          <Stack gap="2" className="py-2">
            <Label htmlFor="detail-instance-label">{t("instanceNameLabel")}</Label>
            <Input
              id="detail-instance-label"
              placeholder={t("instanceNamePlaceholder")}
              value={instanceLabel}
              onChange={(e) => setInstanceLabel(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && instanceLabel.trim()) handleAddInstance();
                if (e.key === "Escape") setAddInstanceOpen(false);
              }}
              autoFocus
            />
            <Text size="xs" tone="muted">
              {t("instanceNameHelp")}
            </Text>
          </Stack>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAddInstanceOpen(false)} disabled={isCreatingInstance}>
              {tCommon("cancel")}
            </Button>
            <Button onClick={handleAddInstance} disabled={!instanceLabel.trim() || isCreatingInstance}>
              {isCreatingInstance ? t("creating") : t("create")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function InstalledPluginRoute({ plugin }: { plugin: PluginInfo }) {
  const queryClient = useQueryClient();
  const router = useRouter();
  const actions = useInstalledPluginActions();
  const { data: connections } = useQuery({ queryKey: OAUTH_CONNECTIONS_QUERY_KEY, queryFn: api.listOAuthConnections });
  const { data: registry } = useQuery({
    queryKey: ["plugin-registry"],
    queryFn: api.listRegistryPlugins,
    staleTime: 5 * 60 * 1000,
  });
  return (
    <PageSection>
      <InstalledPluginRow
        key={plugin.id}
        plugin={plugin}
        fullPage
        connection={findOAuthConnection(connections?.connections, plugin.id)}
        registryEntry={registry?.entries.find((entry) => entry.id === (plugin.base_plugin_id || plugin.id))}
        onToggle={actions.handleToggle}
        isToggling={actions.toggleMutation.isPending}
        onConfigUpdate={() => queryClient.invalidateQueries({ queryKey: ["plugins"] })}
        onUpdate={actions.handleUpdate}
        isUpdating={actions.updatingId === plugin.id}
        onUninstall={async (id) => {
          if (await actions.handleUninstall(id)) router.push("/integrations?tab=installed");
        }}
        isUninstalling={actions.uninstallingId === plugin.id}
      />
    </PageSection>
  );
}

export default function PluginDetailPage() {
  const { pluginId } = useParams<{ pluginId: string }>();
  const { data, isLoading, error } = useQuery({ queryKey: ["plugins"], queryFn: api.listPlugins });
  const t = useTranslations("integrations");
  if (isLoading)
    return (
      <PageSection>
        <Skeleton className="h-32 w-full" />
      </PageSection>
    );
  if (error)
    return (
      <PageSection>
        <Text tone="destructive">{t("loadPluginsError", { error: error instanceof Error ? error.message : "" })}</Text>
      </PageSection>
    );
  const installed = data?.plugins.find((plugin) => plugin.id === pluginId);
  return installed ? <InstalledPluginRoute plugin={installed} /> : <MarketplacePluginDetail />;
}
