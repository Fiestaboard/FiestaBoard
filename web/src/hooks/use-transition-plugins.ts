import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";

import { api, type PluginInfo } from "@/lib/api";

/**
 * The installed transition plugins, for the page and display transition pickers.
 *
 * Read from the plugin listing (`GET /plugins`), filtered to
 * `plugin_type === "transition"`; the Transition Lab's own
 * `/transitions/plugins` endpoint was retired with it. Transition plugins are
 * deprecated: existing `plugin:<id>` strategies keep running, and the pickers
 * keep offering them while the beta flag is on. Shares the `["plugins"]`
 * cache entry with the Integrations page, so installing or removing one there
 * refreshes the pickers too.
 */
export function useTransitionPlugins(enabled: boolean): PluginInfo[] {
  const { data } = useQuery({
    queryKey: ["plugins"],
    queryFn: () => api.listPlugins(),
    enabled,
  });
  return useMemo(() => (data?.plugins ?? []).filter((p) => p.plugin_type === "transition"), [data]);
}
