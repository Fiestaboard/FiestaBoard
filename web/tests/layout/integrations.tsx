import "../../app/globals.css";

import { MainContent } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import { createMemoryRouter, RouterProvider } from "react-router";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";
import { NavigationSidebar } from "@/components/navigation-sidebar";
import { SidebarProvider, useSidebar } from "@/components/sidebar-context";
import { ThemeProvider } from "@/hooks/use-theme";
import i18n from "@/i18n/i18next";

import IntegrationsLayout from "../../app/routes/integrations";
import IntegrationsPage from "../../app/routes/integrations._index";
import PluginDetailPage from "../../app/routes/integrations.$pluginId";

// The seeded bug-bash hub (status/bugbash/instance.md): three built-ins, one
// of them needing setup, plus a deprecated transition.
const plugin = (id: string, name: string, extra: Record<string, unknown> = {}) => ({
  id,
  name,
  category: "utility",
  version: "1.0.0",
  description: `${name} description`,
  author: "FiestaBoard Team",
  enabled: true,
  configured: true,
  icon: "puzzle",
  config: {},
  source: { source_type: "builtin" },
  plugin_type: "data",
  update_available: false,
  instance_label: null,
  base_plugin_id: id,
  ...extra,
});
const plugins = [
  plugin("countdown", "Countdown"),
  plugin("date_time", "Date & Time"),
  plugin("random", "Random", { description: "Display randomly selected values that refresh on an interval" }),
  plugin("weather", "Weather", { configured: false }),
  plugin("quiet_library", "Quiet Library", { plugin_type: "transition" }),
];
const random = {
  ...plugins[2],
  config: { enabled: true, choices: ["TACOS", "PIZZA", "RAMEN", "SALAD"], refresh_seconds: 300 },
  settings_schema: {
    type: "object",
    properties: {
      enabled: { type: "boolean", title: "Enable Random", default: true },
      choices: { type: "array", title: "Choices", items: { type: "string" }, minItems: 2, maxItems: 10 },
      refresh_seconds: { type: "integer", title: "Refresh Interval (seconds)", minimum: 60, maximum: 86400 },
    },
  },
  variables: {},
  env_vars: [],
  has_demo: true,
  demo_page_id: null,
};

const originalFetch = window.fetch;
window.fetch = async (input, init) => {
  const url = new URL(input instanceof Request ? input.url : String(input), location.href);
  if (!url.pathname.startsWith("/api/")) return originalFetch(input, init);
  const path = url.pathname.slice(4);
  let value: unknown = {};
  if (path === "/plugins") value = { plugins, total: plugins.length, enabled_count: 4, plugin_system_enabled: true };
  else if (path === "/plugins/registry") value = { entries: [] };
  else if (path === "/oauth/connections") value = { connections: [], redirect_uri: "" };
  else if (path === "/v1/plugins/random") value = random;
  else if (path === "/v1/plugins/random/data") value = { available: true, data: {} };
  else if (path === "/settings/plugins") value = { auto_update: true };
  else if (path === "/settings/board")
    value = {
      boards: [{ id: "kitchen", name: "Kitchen", device_type: "flagship", output: "vestaboard" }],
      devices: [],
    };
  else if (path === "/v1/status") value = { running: true, configured: true, boards: {} };
  return Response.json(value);
};

const params = new URLSearchParams(location.search);
localStorage.setItem("theme", params.get("theme") === "dark" ? "dark" : "light");
await i18n.changeLanguage(params.get("lang") ?? "en");
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });

function Shell({ children }: { children: React.ReactNode }) {
  const { collapsed } = useSidebar();
  return (
    <>
      <NavigationSidebar />
      <MainContent collapsed={collapsed} railBreakpoint="md" bottomNav>
        {children}
      </MainContent>
    </>
  );
}

const router = createMemoryRouter(
  [
    {
      path: "/integrations",
      element: (
        <Shell>
          <IntegrationsLayout />
        </Shell>
      ),
      children: [
        { index: true, Component: IntegrationsPage },
        { path: ":pluginId", Component: PluginDetailPage },
      ],
    },
  ],
  { initialEntries: [params.get("path") ?? "/integrations?tab=installed"] },
);

createRoot(document.getElementById("root")!).render(
  <I18nextProvider i18n={i18n}>
    <QueryClientProvider client={client}>
      <ThemeProvider defaultTheme={params.get("theme") === "dark" ? "dark" : "light"}>
        <GlobalAiPanelProvider>
          <CurrentBoardProvider>
            <SidebarProvider>
              <RouterProvider router={router} />
            </SidebarProvider>
          </CurrentBoardProvider>
        </GlobalAiPanelProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </I18nextProvider>,
);
