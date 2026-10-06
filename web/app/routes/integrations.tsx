import { useQuery } from "@tanstack/react-query";
import { Puzzle } from "lucide-react";
import { Outlet } from "react-router";

import { PluginUpdatesControl } from "@/components/plugin-updates-control";
import { SectionShell } from "@/components/section-shell";
import { useParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

/**
 * The Integrations section: its card and header stay mounted while the list
 * (/integrations, Installed and Marketplace tabs) and one plugin's page
 * (/integrations/:pluginId) swap beneath them. Plugin updates (auto-update +
 * check now) sit in the header: they act on every plugin in the section.
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

  const detail = pluginId
    ? {
        id: pluginId,
        title: entry?.name ?? (isLoading ? tCommon("loading") : pluginId),
        description: entry?.author ? tDetail("byAuthor", { author: entry.author }) : undefined,
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
      action={<PluginUpdatesControl />}
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
