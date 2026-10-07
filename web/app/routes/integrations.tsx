import { Flex, PluginCategoryBadge, Stack, Text } from "@fiestaboard/ui";
import { useQuery } from "@tanstack/react-query";
import { Puzzle } from "lucide-react";
import { Outlet } from "react-router";

import { PluginUpdateCheckButton } from "@/components/plugin-updates-control";
import { SectionShell } from "@/components/section-shell";
import { useParams } from "@/hooks/use-router";
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

  // The same query the plugin page reads, so the name is in hand from cache.
  const { data: registry, isLoading } = useQuery({
    queryKey: ["plugin-registry"],
    queryFn: api.listRegistryPlugins,
    staleTime: 5 * 60 * 1000,
    enabled: !!pluginId,
  });
  const entry = pluginId ? registry?.entries.find((e) => e.id === pluginId) : undefined;
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
        backHref: "/integrations?tab=marketplace",
      }
    : null;

  return (
    <SectionShell
      icon={Puzzle}
      title={t("title")}
      description={t("description")}
      href="/integrations"
      detail={detail}
      action={<PluginUpdateCheckButton />}
    >
      {children}
    </SectionShell>
  );
}

export default function IntegrationsLayout() {
  return (
    <IntegrationsSection>
      <Outlet />
    </IntegrationsSection>
  );
}
