import { Flex, PluginCategoryBadge, Stack, Text } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { Puzzle } from "lucide-react";
import { useCallback, useState } from "react";
import { Outlet } from "react-router";

import { IntegrationPaneMenuContext } from "@/components/integrations/integration-pane-menu";
import { PluginUpdatesMenu } from "@/components/plugin-updates-control";
import { SectionShell } from "@/components/section-shell";
import { useBelowRail } from "@/hooks/use-below-rail";
import { useParams, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

/** Categories with a translated label under pluginDetail.categories. */
const CATEGORY_KEYS = new Set([
  "art",
  "data",
  "entertainment",
  "finance",
  "home",
  "output",
  "transit",
  "transition",
  "utility",
  "weather",
]);

/**
 * The Integrations section: its card and header stay mounted while the list
 * (/integrations, Installed and Marketplace tabs) and one plugin's page
 * (/integrations/:pluginId) swap beneath them. "Check for updates" is the
 * header's one action: it acts on every plugin in the section. The
 * auto-update switch sits on the Installed tab's toolbar (integrations._index).
 */
export function IntegrationsSection({ children }: { children: React.ReactNode }) {
  const t = useTranslations("integrations");
  const tDetail = useTranslations("pluginDetail");
  const tCommon = useTranslations("common");
  const { pluginId } = useParams<{ pluginId?: string }>();
  // On a phone the list leads with its title alone (Figma 324:50158); the
  // update controls sit under the installed list instead (BB-C-22).
  const phone = useBelowRail();
  const searchParams = useSearchParams();
  const { data: installed } = useQuery({ queryKey: ["plugins"], queryFn: api.listPlugins, enabled: !!pluginId });
  const installedPlugin = installed?.plugins.find((plugin) => plugin.id === pluginId);

  // The same query the plugin page reads, so the name is in hand from cache.
  const { data: registry, isLoading } = useQuery({
    queryKey: ["plugin-registry"],
    queryFn: api.listRegistryPlugins,
    staleTime: 5 * 60 * 1000,
    enabled: !!pluginId,
  });
  // The open detail pane's actions, shown in the header menu (BB-FC-9).
  const [paneItems, setPaneItems] = useState<(() => React.ReactNode) | null>(null);
  const registerPaneItems = useCallback((render: (() => React.ReactNode) | null) => setPaneItems(() => render), []);
  const entry = installedPlugin || (pluginId ? registry?.entries.find((e) => e.id === pluginId) : undefined);
  const category = entry?.category ?? "utility";
  const categoryLabel = CATEGORY_KEYS.has(category) ? tDetail(`categories.${category}`) : category;

  // Everything that says what the plugin IS sits under its name: what it does,
  // then its category, who made it and what it needs. It used to be a hero
  // card of its own; split across the sub-header and an untitled block below a
  // full-width board, half of it ended up below the fold.
  const about = entry && (
    <Stack gap="2" className="mt-1">
      {entry.description && <Text tone="muted">{entry.description}</Text>}
      <Flex align="center" gap="3" wrap>
        <PluginCategoryBadge category={category} label={categoryLabel} />
        {entry.author && (
          <Text as="span" size="sm" tone="muted">
            {tDetail("byAuthor", { author: entry.author })}
          </Text>
        )}
        {entry.fiestaboard_version && (
          <Text as="span" size="xs" tone="muted">
            {tDetail("requiresFiestaboard", { version: entry.fiestaboard_version })}
          </Text>
        )}
      </Flex>
    </Stack>
  );

  const detail = pluginId
    ? {
        id: pluginId,
        title: entry?.name ?? (isLoading ? tCommon("loading") : pluginId),
        description: about || undefined,
        // Plugin pages are opened from the Marketplace; going back lands on it.
        backHref:
          installedPlugin || searchParams.get("from") === "installed"
            ? "/integrations?tab=installed"
            : "/integrations?tab=marketplace",
      }
    : null;

  return (
    <IntegrationPaneMenuContext.Provider value={registerPaneItems}>
      <SectionShell
        icon={Puzzle}
        title={t("title")}
        description={phone ? undefined : t("description")}
        href="/integrations"
        detail={detail}
        // 07d `324:40267`: a "…" button is the header's one action, and the
        // list sits on the page rather than in a card (BB-FC-8).
        action={phone ? undefined : <PluginUpdatesMenu paneItems={paneItems} />}
        surface="plain"
      >
        {children}
      </SectionShell>
    </IntegrationPaneMenuContext.Provider>
  );
}

export default function IntegrationsLayout() {
  return (
    <IntegrationsSection>
      <Outlet />
    </IntegrationsSection>
  );
}
