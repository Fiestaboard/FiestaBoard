import "../../app/globals.css";

import { MainContent } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createRoot } from "react-dom/client";
import { I18nextProvider } from "react-i18next";
import { MemoryRouter, Route, Routes } from "react-router";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";
import { NavigationSidebar } from "@/components/navigation-sidebar";
import { ScheduleEditorBridgeProvider } from "@/components/schedule-editor-bridge-context";
import { SidebarProvider, useSidebar } from "@/components/sidebar-context";
import { useRailBreakpoint } from "@/hooks/use-below-rail";
import { ThemeProvider } from "@/hooks/use-theme";
import i18n from "@/i18n/i18next";
import type { ActiveScheduleResponse, ScheduleEntry } from "@/lib/api";

import SchedulePage from "../../app/routes/schedule";

const params = new URLSearchParams(location.search);
const theme = params.get("theme") === "dark" ? "dark" : "light";
const empty = params.get("state") === "empty";
localStorage.setItem("theme", theme);
localStorage.removeItem("schedule-view-mode");

const boards = [
  {
    id: "kitchen",
    name: "Kitchen board",
    device_type: "flagship",
    board_color: "black",
    enabled: true,
    schedule_enabled: true,
    paused: false,
  },
  {
    id: "source",
    name: "Source display",
    device_type: "flagship",
    board_color: "black",
    enabled: true,
    schedule_enabled: true,
  },
];
const pages = [
  {
    id: "morning",
    name: "Breakfast specials",
    type: "template",
    device_type: "flagship",
    template: ["BREAKFAST SPECIALS", "COFFEE AND TOAST", "", "", "", ""],
    duration_seconds: 30,
    created_at: "2026-11-01T00:00:00Z",
  },
  {
    id: "lunch",
    name: "Lunch menu",
    type: "template",
    device_type: "flagship",
    template: ["LUNCH MENU", "SOUP AND SANDWICH", "", "", "", ""],
    duration_seconds: 30,
    created_at: "2026-11-01T00:00:00Z",
  },
  {
    id: "rainy",
    name: "Rainy-day specials",
    type: "template",
    device_type: "flagship",
    template: ["RAINY DAY SPECIALS", "HOT SOUP", "", "", "", ""],
    duration_seconds: 30,
    created_at: "2026-11-01T00:00:00Z",
  },
];
const make = (id: string, page_id: string, start_time: string, end_time: string): ScheduleEntry => ({
  id,
  board_id: "kitchen",
  page_id,
  start_time,
  end_time,
  start_type: "fixed",
  end_type: "fixed",
  day_pattern: "all",
  recurrence_type: "weekly",
  enabled: true,
  created_at: "2026-11-01T00:00:00Z",
  edit_protocol: "schedule-revision-v1",
  revision: `${id}-1`,
});
let entries = empty ? [] : [make("breakfast", "morning", "09:00", "13:00"), make("lunch", "lunch", "12:00", "15:00")];
const source = [make("source-entry", "morning", "08:00", "11:00")];
let revision = 1;
const originalFetch = window.fetch;
window.fetch = async (input, init) => {
  const url = new URL(input instanceof Request ? input.url : String(input), location.href);
  if (!url.pathname.startsWith("/api/")) return originalFetch(input, init);
  const path = decodeURIComponent(url.pathname.slice(4));
  const method = init?.method ?? "GET";
  const body = init?.body ? JSON.parse(String(init.body)) : {};
  let value: unknown = {};
  if (path === "/settings/board") value = { boards, board_type: "black", devices: ["flagship"] };
  else if (path === "/v1/status")
    value = {
      running: true,
      configured: true,
      boards: Object.fromEntries(
        boards.map((board) => [
          board.id,
          {
            configured: true,
            paused: false,
            active_page_id: "morning",
            health: {
              reachable: true,
              latency_ms: 42,
              breaker_open: false,
              last_connected_at: "2026-11-17T02:17:00Z",
              last_error: null,
            },
          },
        ]),
      ),
    };
  else if (path === "/settings/all")
    value = {
      display: { reduce_motion: true, board_animations: "off", site_animations: "off" },
      general: { timezone: "America/Los_Angeles", instance_name: "Cafe hub" },
      silence_schedule: {
        config: {
          enabled: true,
          start_time: "06:00+00:00",
          end_time: "15:00+00:00",
          mode: "indicator",
          indicator_text: "SNOOZING",
          page_id: null,
        },
      },
    };
  else if (path === "/v1/pages") value = { pages, total: pages.length };
  else if (path.startsWith("/v1/pages/")) value = pages.find((page) => page.id === path.split("/").at(-1));
  else if (path === "/v1/collections")
    value = {
      collections: [
        {
          id: "collection:rules",
          name: "Weather specials",
          page_ids: ["morning", "rainy"],
          selection_mode: "variable",
          time: { interval_seconds: 60 },
          variable: {
            rules: [{ expression: "weather.temperature < 70", page_id: "rainy" }],
            default_page_id: "morning",
            poll_seconds: 60,
          },
        },
      ],
      total: 1,
    };
  else if (path === "/v1/schedules") {
    if (method === "POST") {
      const entry = {
        ...body,
        id: `created-${++revision}`,
        revision: `r${revision}`,
        edit_protocol: "schedule-revision-v1",
        created_at: "2026-11-17T02:18:00Z",
      };
      entries = [...entries, entry];
      value = { ...entry, warnings: [] };
    } else
      value = {
        schedules: url.searchParams.get("board_id") === "source" ? source : entries,
        total: entries.length,
        enabled: true,
        default_page_id: "morning",
      };
  } else if (path.startsWith("/v1/schedules/")) {
    const id = path.split("/").at(-1)!;
    if (method === "DELETE") {
      entries = entries.filter((entry) => entry.id !== id);
      value = { id };
    } else {
      entries = entries.map((entry) => (entry.id === id ? { ...entry, ...body, revision: `r${++revision}` } : entry));
      value = { ...entries.find((entry) => entry.id === id), warnings: [] };
    }
  } else if (path === "/schedules/validate")
    value = {
      valid: false,
      overlaps:
        entries.some((entry) => entry.id === "breakfast") &&
        entries.some((entry) => entry.id === "lunch" && entry.start_time < "13:00")
          ? [
              {
                schedule1_id: "breakfast",
                schedule2_id: "lunch",
                conflict_description:
                  "Lunch menu overlaps Breakfast specials. The most recent start wins within weekly entries.",
              },
            ]
          : [],
      gaps: [
        {
          start_time: "15:00",
          end_time: "22:00",
          days: ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
        },
      ],
    };
  else if (path === "/schedules/active/page")
    value = {
      page_id: "morning",
      resolved_page_id: "morning",
      resolved_next_check_seconds: null,
      source: "schedule",
      schedule_enabled: true,
      current_day: "monday",
      current_time: "18:18",
      default_page_id: "morning",
      at: url.searchParams.get("at"),
      silenced: false,
      temporary_override: {
        active: false,
        page_id: null,
        expires_at: null,
        remaining_seconds: null,
        revert_mode: null,
        revert_page_id: null,
      },
    } satisfies ActiveScheduleResponse;
  else if (path === "/collections/collection:rules/dry-run")
    value = {
      collection_id: "collection:rules",
      selection_mode: "variable",
      at: body.at,
      page_id: "rainy",
      matched_rule: 0,
      rules: [
        {
          index: 0,
          expression: "weather.temperature < 70",
          page_id: "rainy",
          value: "true",
          matched: true,
          error: null,
          message: null,
        },
        {
          index: 1,
          expression: "HOUR(NOW()) >= 15",
          page_id: "morning",
          value: "true",
          matched: true,
          error: null,
          message: null,
        },
      ],
      timeline: [
        { from: "2026-11-17T02:00:00Z", until: "2026-11-17T05:00:00Z", page_id: "rainy" },
        { from: "2026-11-17T05:00:00Z", until: "2026-11-17T10:00:00Z", page_id: "morning" },
      ],
      shown_on: ["kitchen"],
      sources: { weather: { state: "stale", updated_at: "2026-11-17T01:41:00Z" } },
      truncated: false,
    };
  else if (path === "/templates/render") {
    const lines = body.template ?? [];
    value = { lines, rendered: lines.join("\n"), line_count: lines.length };
  } else if (path === "/settings/location") value = { latitude: null, longitude: null };
  else if (path === "/plugins") value = { plugins: [], total: 0 };
  else if (path.startsWith("/silence")) value = { active: false, enabled: false };
  else if (path === "/auth/sessions") value = { sessions: [], total: 0 };
  else if (path.startsWith("/v1/boards/")) {
    const board = boards.find((item) => item.id === path.split("/").at(-1));
    if (method === "PATCH" && board) Object.assign(board, body);
    value = { ...board, active_page_id: "morning", resolved_page_id: "morning", default_page_id: "morning" };
  }
  return Response.json(value ?? {});
};
const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
function Fixture() {
  const { collapsed } = useSidebar();
  // The app's breakpoint (MainContent): a short landscape phone keeps the
  // phone chrome up to lg (BB-A-13), so the content clears its header.
  const railBreakpoint = useRailBreakpoint();
  return (
    <>
      <NavigationSidebar />
      <MainContent collapsed={collapsed} railBreakpoint={railBreakpoint} bottomNav>
        <Routes>
          <Route path="/schedule" element={<SchedulePage />} />
        </Routes>
      </MainContent>
    </>
  );
}
createRoot(document.getElementById("root")!).render(
  <MemoryRouter initialEntries={["/schedule"]}>
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={client}>
        <ThemeProvider defaultTheme={theme}>
          <GlobalAiPanelProvider>
            <CurrentBoardProvider>
              <SidebarProvider>
                <ScheduleEditorBridgeProvider>
                  <Fixture />
                </ScheduleEditorBridgeProvider>
              </SidebarProvider>
            </CurrentBoardProvider>
          </GlobalAiPanelProvider>
        </ThemeProvider>
      </QueryClientProvider>
    </I18nextProvider>
  </MemoryRouter>,
);
