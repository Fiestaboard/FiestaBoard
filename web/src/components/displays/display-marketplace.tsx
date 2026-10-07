"use client";

/**
 * Displays → Marketplace: every display FiestaBoard can drive, on the same
 * `PluginCard` the Integrations marketplace (and fiestaboard.app/plugins)
 * uses, so people can see displays are expandable the way integrations are.
 *
 * The list is `GET /outputs/available` — the outputs on this FiestaBoard
 * (Vestaboard and FiestaPanel first), then the ones it can install: bundled
 * with the image (installs offline) or listed in the plugin registry. No
 * opt-in gates any of them (settings v7). A card's action is what the display
 * needs next: Install, or Add display (plus Update when the plugin has one,
 * from `GET /plugins`). The card's link opens the add flow for that display
 * (`/displays?tab=marketplace&add=<id>`); the page owns the dialog. "Bring
 * your own display" side-loads a display plugin from a git URL.
 */
import {
  Alert,
  AlertDescription,
  AlertTitle,
  Box,
  Button,
  Flex,
  Grid,
  Heading,
  Input,
  PluginCard,
  Stack,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { EmptyState } from "@fiestaboard/ui/components/feedback/empty-state";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDownToLine, Download, Plus, RefreshCw, Search } from "lucide-react";
import { useId, useState } from "react";
import { toast } from "sonner";

import { GitInstallFields, useGitPluginInstall } from "@/components/plugin-git-install";
import { AVAILABLE_OUTPUTS_QUERY_KEY, OUTPUTS_QUERY_KEY } from "@/components/settings/output-boards";
import Link from "@/components/smart-link";
import { useTranslations } from "@/i18n/translations";
import type { AvailableOutput } from "@/lib/api";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

/** Where "Write a display plugin" points: the output plugin author's guide. */
export const OUTPUT_PLUGIN_GUIDE_URL = "https://fiestaboard.app/docs/development/output-plugins";

/** The add flow for *outputId*, as a link (the Displays page opens it). */
export function addDisplayHref(outputId: string): string {
  return `/displays?tab=marketplace&add=${encodeURIComponent(outputId)}`;
}

export function DisplayMarketplace({ onAdd }: { onAdd: (output: { id: string; name: string }) => void }) {
  const t = useTranslations("displays.marketplace");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [query, setQuery] = useState("");
  const installedHeadingId = useId();
  const availableHeadingId = useId();

  const outputs = useQuery({
    queryKey: AVAILABLE_OUTPUTS_QUERY_KEY,
    queryFn: () => api.listAvailableOutputs(),
    staleTime: 60_000,
  });
  // Attribution only: a registry entry carries its author.
  const registry = useQuery({
    queryKey: ["plugin-registry"],
    queryFn: () => api.listRegistryPlugins(),
    staleTime: 5 * 60_000,
  });
  // Which installed display plugins have an update.
  const plugins = useQuery({ queryKey: ["plugins"], queryFn: () => api.listPlugins() });

  const authorOf = (id: string) => registry.data?.entries.find((entry) => entry.id === id)?.author || null;
  const hasUpdate = (id: string) => plugins.data?.plugins.some((p) => p.id === id && p.update_available) ?? false;

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: OUTPUTS_QUERY_KEY });
    void queryClient.invalidateQueries({ queryKey: ["plugins"] });
    void queryClient.invalidateQueries({ queryKey: ["plugin-registry"] });
  };
  const errorText = (err: unknown) => (err instanceof Error ? err.message : tCommon("unknownError"));

  const install = useMutation({
    mutationFn: (output: AvailableOutput) => api.installOutput(output.id),
    onSuccess: (_result, output) => {
      toast.success(t("toastInstalled", { name: output.name }));
      refresh();
    },
    onError: (err, output) => toast.error(t("toastInstallFailed", { name: output.name, error: errorText(err) })),
  });
  const update = useMutation({
    mutationFn: (output: AvailableOutput) => api.updatePlugin(output.id),
    onSuccess: (_result, output) => {
      toast.success(t("toastUpdated", { name: output.name }));
      refresh();
    },
    onError: (err, output) => toast.error(t("toastUpdateFailed", { name: output.name, error: errorText(err) })),
  });

  const needle = query.trim().toLowerCase();
  const shown = (outputs.data ?? []).filter(
    (o) => !needle || o.name.toLowerCase().includes(needle) || o.description.toLowerCase().includes(needle),
  );
  const installed = shown.filter((o) => o.installed);
  const toInstall = shown.filter((o) => !o.installed);

  const card = (output: AvailableOutput, index: number) => {
    const author = authorOf(output.id);
    const installing = install.isPending && install.variables?.id === output.id;
    const updating = update.isPending && update.variables?.id === output.id;
    const authorLabel = author
      ? t("byAuthor", { author })
      : output.installed
        ? undefined
        : output.needs_network
          ? t("downloads")
          : t("installsOffline");
    return (
      <PluginCard
        key={output.id}
        className="animate-card-fade-in"
        style={{ animationDelay: `${index * 60}ms` }}
        name={output.name}
        description={output.description}
        authorLabel={authorLabel}
        renderLink={({ className, children }) => (
          <Link href={addDisplayHref(output.id)} className={className}>
            {children}
          </Link>
        )}
        action={
          output.installed ? (
            <Flex gap="2">
              {hasUpdate(output.id) && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 text-xs"
                  onClick={() => update.mutate(output)}
                  disabled={updating}
                  aria-label={t("updateLabel", { name: output.name })}
                >
                  <RefreshCw className={cn("mr-1 h-3 w-3", updating && "animate-spin")} aria-hidden="true" />
                  {updating ? t("updating") : t("update")}
                </Button>
              )}
              <Button
                size="sm"
                className="h-8 text-xs"
                onClick={() => onAdd({ id: output.id, name: output.name })}
                aria-label={t("addLabel", { name: output.name })}
              >
                <Plus className="mr-1 h-3 w-3" aria-hidden="true" />
                {t("add")}
              </Button>
            </Flex>
          ) : (
            <Button
              size="sm"
              variant="outline"
              className="h-8 text-xs"
              onClick={() => install.mutate(output)}
              disabled={installing}
              aria-label={t("installLabel", { name: output.name })}
            >
              <ArrowDownToLine className={cn("mr-1 h-3 w-3", installing && "animate-bounce")} aria-hidden="true" />
              {installing ? t("installing") : t("install")}
            </Button>
          )
        }
      />
    );
  };

  return (
    <Stack gap="6" data-testid="display-marketplace">
      <Box className="relative w-full md:max-w-md">
        <Search
          className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden="true"
        />
        <Input
          type="search"
          aria-label={t("searchLabel")}
          placeholder={t("searchPlaceholder")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          className="w-full pl-9"
        />
      </Box>

      {outputs.isLoading ? (
        <Flex align="center" gap="2" role="status">
          <Spinner label={null} />
          <Text as="span" tone="muted">
            {t("loading")}
          </Text>
        </Flex>
      ) : outputs.isError ? (
        <Alert variant="destructive">
          <AlertDescription>
            <Stack gap="2">
              <Text size="sm">{t("loadFailed")}</Text>
              <Flex>
                <Button type="button" size="sm" variant="outline" onClick={() => void outputs.refetch()}>
                  {t("retry")}
                </Button>
              </Flex>
            </Stack>
          </AlertDescription>
        </Alert>
      ) : shown.length === 0 ? (
        <EmptyState icon={Search} title={t("noMatch", { query })} className="py-16" />
      ) : (
        <>
          {installed.length > 0 && (
            <Box as="section" aria-labelledby={installedHeadingId}>
              <Heading level={2} size="sm" id={installedHeadingId} className="mb-3">
                {t("installedHeading")}
              </Heading>
              <Grid cols="1" md="2" gap="4" className="items-stretch xl:grid-cols-3">
                {installed.map((output, index) => card(output, index))}
              </Grid>
            </Box>
          )}
          {toInstall.length > 0 && (
            <Box as="section" aria-labelledby={availableHeadingId}>
              <Heading level={2} size="sm" id={availableHeadingId} className="mb-3">
                {t("availableHeading")}
              </Heading>
              <Grid cols="1" md="2" gap="4" className="items-stretch xl:grid-cols-3">
                {toInstall.map((output, index) => card(output, installed.length + index))}
              </Grid>
            </Box>
          )}
        </>
      )}

      <BringYourOwnDisplay onAdd={onAdd} />
    </Stack>
  );
}

type SideLoadOutcome =
  | { kind: "display"; id: string; name: string }
  | { kind: "data"; pluginId: string }
  | { kind: "error"; message: string };

/**
 * "Bring your own display": side-load a display plugin from its git
 * repository (the same `POST /plugins/install` as Integrations → Install
 * Plugin from Git), then add a display with it. A repository that holds a
 * data plugin installs too, and is pointed at Integrations.
 */
function BringYourOwnDisplay({ onAdd }: { onAdd: (output: { id: string; name: string }) => void }) {
  const t = useTranslations("displays.marketplace");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const gitInstall = useGitPluginInstall();
  const [outcome, setOutcome] = useState<SideLoadOutcome | null>(null);
  const failedTitleId = useId();

  const sideLoad = async () => {
    setOutcome(null);
    let pluginId: string;
    try {
      pluginId = await gitInstall.install();
    } catch (err) {
      setOutcome({ kind: "error", message: err instanceof Error ? err.message : tCommon("unknownError") });
      return;
    }
    gitInstall.reset();
    const outputs = await queryClient
      .fetchQuery({ queryKey: AVAILABLE_OUTPUTS_QUERY_KEY, queryFn: () => api.listAvailableOutputs(), staleTime: 0 })
      .catch(() => [] as AvailableOutput[]);
    const output = outputs.find((o) => o.id === pluginId && o.installed);
    setOutcome(output ? { kind: "display", id: output.id, name: output.name } : { kind: "data", pluginId });
  };

  return (
    <Stack gap="3" className="rounded-xl border border-dashed p-4" data-testid="display-marketplace-build">
      <Heading level={2} size="sm">
        {t("buildTitle")}
      </Heading>
      <Text size="sm" tone="muted">
        {t("buildBody")}
      </Text>
      <GitInstallFields
        install={gitInstall}
        idPrefix="display-git"
        urlPlaceholder="https://github.com/user/fiestaboard-output--my-display.git"
      />
      <Flex align="center" gap="3" wrap>
        <Button
          type="button"
          size="sm"
          onClick={() => void sideLoad()}
          disabled={gitInstall.isInstalling || !gitInstall.canInstall}
        >
          <Download
            className={cn("mr-1 h-3.5 w-3.5", gitInstall.isInstalling && "animate-bounce")}
            aria-hidden="true"
          />
          {gitInstall.isInstalling ? t("installing") : t("gitInstall")}
        </Button>
        <Text size="sm">
          <TextLink href={OUTPUT_PLUGIN_GUIDE_URL} target="_blank" rel="noopener noreferrer">
            {t("buildLink")}
          </TextLink>
        </Text>
      </Flex>

      {outcome?.kind === "display" && (
        <Alert variant="success">
          <AlertDescription>
            <Flex align="center" justify="between" gap="3" wrap>
              <Text size="sm">{t("toastInstalled", { name: outcome.name })}</Text>
              <Button
                type="button"
                size="sm"
                onClick={() => onAdd({ id: outcome.id, name: outcome.name })}
                aria-label={t("addLabel", { name: outcome.name })}
              >
                <Plus className="mr-1 h-3 w-3" aria-hidden="true" />
                {t("add")}
              </Button>
            </Flex>
          </AlertDescription>
        </Alert>
      )}
      {outcome?.kind === "data" && (
        <Alert>
          <AlertDescription>
            <Flex align="center" justify="between" gap="3" wrap>
              <Text size="sm">{t("gitInstalledData", { pluginId: outcome.pluginId })}</Text>
              <Button asChild type="button" size="sm" variant="outline">
                <Link href="/integrations?tab=installed">{t("gitOpenIntegrations")}</Link>
              </Button>
            </Flex>
          </AlertDescription>
        </Alert>
      )}
      {outcome?.kind === "error" && (
        <Alert variant="destructive" aria-labelledby={failedTitleId}>
          <AlertTitle id={failedTitleId}>{t("gitFailedTitle")}</AlertTitle>
          <AlertDescription>{outcome.message}</AlertDescription>
        </Alert>
      )}
    </Stack>
  );
}
