import "../../app/globals.css";

import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import { createMemoryRouter, Outlet, RouterProvider } from "react-router";

import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";
import { MainContent } from "@/components/main-content";
import { NavigationSidebar } from "@/components/navigation-sidebar";
import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { PageFadeWrapper } from "@/components/page-fade-wrapper";
import { Providers } from "@/components/providers";
import { ScheduleEditorBridgeProvider } from "@/components/schedule-editor-bridge-context";
import { WizardProvider } from "@/components/wizard-provider";
import i18n from "@/i18n/i18next";

import CollectionsLayout from "../../app/routes/collections";
import CollectionsPage from "../../app/routes/collections._index";
import DisplaysLayout from "../../app/routes/displays";
import DisplaysPage from "../../app/routes/displays._index";
import DisplayPage from "../../app/routes/displays.$boardId";
import Home from "../../app/routes/home";
import IntegrationsLayout from "../../app/routes/integrations";
import IntegrationsPage from "../../app/routes/integrations._index";
import NotFound from "../../app/routes/not-found";
import PagesLayout from "../../app/routes/pages";
import PagesPage from "../../app/routes/pages._index";
import Picks from "../../app/routes/picks";
import Schedule from "../../app/routes/schedule";
import Settings from "../../app/routes/settings";
import outputs from "../../src/__tests__/mocks/first-party-outputs.json";

/**
 * Every top-level route in the real shell (rail, MainContent, PageFadeWrapper)
 * over a mocked hub, for the flat page grammar's spacing (page-grammar.spec).
 * `?path=/displays` picks the route.
 */
const boards = [
  { id: "kitchen", name: "Kitchen board", device_type: "flagship", board_color: "black", output: "vestaboard" },
  { id: "fridge", name: "Fridge note", device_type: "note", board_color: "black", output: "vestaboard" },
].map((board) => ({
  paused: false,
  schedule_enabled: true,
  output_config: { api_mode: "local", host: "fiestapi.local" },
  ...board,
}));
const page = (id: string, name: string) => ({
  id,
  name,
  type: "single",
  template: ["GOOD EVENING", "", "CLEAR 64"],
  board_id: "kitchen",
  device_type: "flagship",
  updated_at: "2026-11-16T09:41:00Z",
  created_at: "2026-11-16T09:41:00Z",
});
const pages = [page("evening", "Evening commute"), page("morning", "Kitchen morning"), page("night", "Good night")];
const health = { reachable: true, breaker_open: false, latency_ms: 42, last_connected_at: "2026-11-16T09:41:00Z" };

const originalFetch = window.fetch;
window.fetch = async (input, init) => {
  const url = new URL(input instanceof Request ? input.url : String(input), location.href);
  if (!url.pathname.startsWith("/api/")) return originalFetch(input, init);
  const path = url.pathname.slice(4);
  let value: unknown = {};
  if (path === "/settings/board") value = { boards, board_type: "black", devices: ["flagship"] };
  else if (path === "/v1/status")
    value = {
      running: true,
      configured: true,
      boards: Object.fromEntries(
        boards.map((b) => [b.id, { configured: true, paused: false, active_page_id: "evening", health }]),
      ),
    };
  else if (path === "/outputs") value = outputs;
  else if (path === "/outputs/available") value = [];
  else if (path === "/v1/pages" || path === "/pages") value = { pages, total: pages.length };
  else if (path.startsWith("/v1/pages/") || path.startsWith("/pages/"))
    value = pages.find((p) => path.endsWith(p.id)) ?? pages[0];
  else if (path === "/v1/collections") value = { collections: [], total: 0 };
  else if (path === "/plugins") value = { plugins: [], total: 0 };
  else if (path.startsWith("/plugins/marketplace") || path === "/registry/plugins") value = { plugins: [], total: 0 };
  else if (path === "/panels") value = { panels: [], total: 0 };
  else if (path === "/auth/sessions") value = { sessions: [], total: 0 };
  else if (path === "/v1/schedules") value = { schedules: [], total: 0, enabled: true, default_page_id: "evening" };
  else if (path === "/schedules/validate") value = { valid: true, overlaps: [], gaps: [] };
  else if (path === "/settings/location") value = { latitude: null, longitude: null };
  else if (path.startsWith("/schedules/active")) value = { page_id: "evening", page: pages[0] };
  else if (path.startsWith("/silence")) value = { active: false, enabled: false };
  else if (path === "/settings/all")
    value = { display: {}, general: { timezone: "America/Los_Angeles" }, silence_schedule: { config: {} } };
  else if (path === "/staff-picks") value = [];
  else if (path === "/system/update-check")
    value = {
      current_version: "11.0.0",
      latest_version: params.get("update") ? "11.1.0" : "11.0.0",
      update_available: !!params.get("update"),
      package_url: "",
      error: null,
      is_production: true,
    };
  else if (path === "/system/update/status") value = { updater_available: false, auto_update_enabled: false };
  else if (path.startsWith("/templates/render")) value = { lines: [], rendered: "", line_count: 0 };
  else if (path.endsWith("/current-message"))
    value = { message: "", characters: Array.from({ length: 6 }, () => Array(22).fill(0)), rows: 6, cols: 22 };
  else if (path.startsWith("/v1/boards/")) value = { ...boards[0], resolved_page_id: "evening", next_page_id: "night" };
  return Response.json(value);
};

const params = new URLSearchParams(location.search);
localStorage.setItem("theme", params.get("theme") === "dark" ? "dark" : "light");
localStorage.setItem("fiestaboard_wizard_complete", "true");
localStorage.setItem("fiestaboard_site_animations", "false");

function Shell() {
  return (
    <Providers>
      <ScheduleEditorBridgeProvider>
        <PageEditorBridgeProvider>
          <GlobalAiPanelProvider>
            <WizardProvider>
              <NavigationSidebar />
              <MainContent>
                <PageFadeWrapper>
                  <Outlet />
                </PageFadeWrapper>
              </MainContent>
            </WizardProvider>
          </GlobalAiPanelProvider>
        </PageEditorBridgeProvider>
      </ScheduleEditorBridgeProvider>
    </Providers>
  );
}

const router = createMemoryRouter(
  [
    {
      element: <Shell />,
      children: [
        { index: true, element: <Home /> },
        { path: "pages", element: <PagesLayout />, children: [{ index: true, element: <PagesPage /> }] },
        {
          path: "collections",
          element: <CollectionsLayout />,
          children: [{ index: true, element: <CollectionsPage /> }],
        },
        {
          path: "displays",
          element: <DisplaysLayout />,
          children: [
            { index: true, element: <DisplaysPage /> },
            { path: ":boardId", element: <DisplayPage /> },
          ],
        },
        {
          path: "integrations",
          element: <IntegrationsLayout />,
          children: [{ index: true, element: <IntegrationsPage /> }],
        },
        { path: "schedule", element: <Schedule /> },
        { path: "settings/:section?", element: <Settings /> },
        { path: "picks", element: <Picks /> },
        { path: "*", element: <NotFound /> },
      ],
    },
  ],
  { initialEntries: [params.get("path") ?? "/"] },
);

createRoot(document.getElementById("root")!).render(
  <I18nextProvider i18n={i18n}>
    <RouterProvider router={router} />
  </I18nextProvider>,
);
