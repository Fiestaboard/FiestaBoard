import "../../app/globals.css";

import { MainContent } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes } from "react-router";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";
import { NavigationSidebar } from "@/components/navigation-sidebar";
import { SidebarProvider, useSidebar } from "@/components/sidebar-context";
import { ThemeProvider } from "@/hooks/use-theme";
import i18n from "@/i18n/i18next";

import DisplaysLayout from "../../app/routes/displays";
import DisplaysPage from "../../app/routes/displays._index";
import DisplayPage from "../../app/routes/displays.$boardId";
import outputs from "../../src/__tests__/mocks/first-party-outputs.json";

const boards = [
  {
    id: "kitchen",
    name: "Kitchen board",
    device_type: "flagship",
    board_color: "black",
    output: "vestaboard",
    paused: false,
    schedule_enabled: true,
  },
  {
    id: "entry",
    name: "Entry clock",
    device_type: "flagship",
    board_color: "black",
    output: "vestaboard",
    paused: false,
  },
  {
    id: "desk",
    name: "Desk Pixoo",
    device_type: "panel",
    grid_rows: 8,
    grid_cols: 10,
    output: "divoom_pixoo",
    device_model: "divoom_pixoo64",
    paused: false,
  },
];
const health = (reachable: boolean) => ({
  reachable,
  breaker_open: false,
  latency_ms: 42,
  last_connected_at: "2026-11-16T09:41:00Z",
  last_update_at: "2026-11-16T09:41:00Z",
  last_error_at: reachable ? null : "2026-11-16T09:42:00Z",
  last_error: reachable ? null : "timeout",
});
const originalFetch = window.fetch;
window.fetch = async (input, init) => {
  const url = new URL(input instanceof Request ? input.url : String(input), location.href);
  if (!url.pathname.startsWith("/api/")) return originalFetch(input, init);
  const path = url.pathname.slice(4);
  let value: unknown = {};
  if (path === "/settings/board") value = { boards, board_type: "black", devices: [] };
  else if (path === "/v1/status")
    value = {
      running: true,
      configured: true,
      boards: Object.fromEntries(
        boards.map((board) => [
          board.id,
          { configured: true, paused: board.paused, active_page_id: "evening", health: health(board.id !== "entry") },
        ]),
      ),
    };
  else if (path === "/outputs") value = outputs;
  else if (path === "/outputs/available") value = [];
  else if (path === "/pages")
    value = {
      pages: [
        { id: "evening", name: "Evening commute" },
        { id: "night", name: "Good night" },
      ],
      total: 2,
    };
  else if (path === "/panels") value = { panels: [], total: 0 };
  else if (path === "/plugins") value = { plugins: [], total: 0 };
  else if (path === "/settings/all") value = { display: {}, general: {} };
  else if (path.startsWith("/silence")) value = { active: false, enabled: false };
  else if (path.endsWith("/current-message"))
    value = { message: "GOOD EVENING\n64 CLEAR", characters: [[1]], expected_characters: [[1]], rows: 6, cols: 22 };
  else if (path.startsWith("/v1/boards/")) {
    const board = boards.find((item) => item.id === path.split("/")[3]);
    if (board && init?.method === "PATCH") Object.assign(board, JSON.parse(String(init.body)));
    value = {
      ...board,
      resolved_page_id: "evening",
      next_change_at: "2026-11-16T21:00:00Z",
      next_change_reason: "schedule",
      next_page_id: "night",
    };
  }
  return Response.json(value);
};
const theme = new URLSearchParams(location.search).get("theme") === "dark" ? "dark" : "light";
localStorage.setItem("theme", theme);
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
function Fixture() {
  const { collapsed } = useSidebar();
  return (
    <>
      <NavigationSidebar />
      <MainContent collapsed={collapsed} railBreakpoint="md" bottomNav>
        <Routes>
          <Route path="/displays" element={<DisplaysLayout />}>
            <Route index element={<DisplaysPage />} />
            <Route path=":boardId" element={<DisplayPage />} />
          </Route>
        </Routes>
      </MainContent>
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <MemoryRouter initialEntries={["/displays"]}>
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <ThemeProvider defaultTheme={theme}>
          <GlobalAiPanelProvider>
            <CurrentBoardProvider>
              <SidebarProvider>
                <Fixture />
              </SidebarProvider>
            </CurrentBoardProvider>
          </GlobalAiPanelProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </I18nextProvider>
  </MemoryRouter>,
);
