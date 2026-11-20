import type { Page } from "@playwright/test";

import outputs from "../../src/__tests__/mocks/first-party-outputs.json" with { type: "json" };

// The hub behind the Creator IDE layout specs (creator-ide, editor-window):
// every response the saved-page editor asks for. `deviceType` opens the
// same page as another board kind (D2: the Explorer's default follows it).

export interface CreatorIdeHubOptions {
  deviceType?: "flagship" | "note" | "note_array" | "panel";
  /** The page is on no display and in no schedule: the header offers Save / Show now. */
  notScheduled?: boolean;
}

export const board = {
  id: "kitchen-board",
  name: "Kitchen board",
  device_type: "flagship",
  board_color: "black",
  enabled: true,
  output: "vestaboard",
};
export const kitchenMorning = {
  id: "kitchen-morning",
  name: "Kitchen morning",
  type: "template",
  device_type: "flagship",
  template: ["GOOD MORNING", "", "{{weather.temperature}} SUNNY", '{{= DEFAULT(weather.alert, "OK") }}', "", ""],
  duration_seconds: 30,
  revision: "r-live",
  line_metadata: Array.from({ length: 6 }, () => ({ alignment: "center", wrap: false })),
};
const revisions = [
  {
    id: "r2",
    saved_at: "2026-11-17T15:12:00Z",
    origin: "edited",
    via: "web",
    name: kitchenMorning.name,
    rows: 6,
    cols: 22,
    current: true,
  },
  {
    id: "r1",
    saved_at: "2026-11-16T21:02:00Z",
    origin: "assistant",
    via: "mcp",
    name: kitchenMorning.name,
    rows: 6,
    cols: 22,
    current: false,
  },
];

export async function mockHub(page: Page, options: CreatorIdeHubOptions = {}) {
  const deviceType = options.deviceType ?? kitchenMorning.device_type;
  const opened = {
    ...kitchenMorning,
    device_type: deviceType,
    ...(deviceType === "panel" && { grid_rows: 14, grid_cols: 34 }),
  };
  // What the display shows: this page (live), or another one.
  const showing = options.notScheduled ? "evening" : kitchenMorning.id;
  await page.route(
    (url) => url.pathname.startsWith("/api/"),
    async (route) => {
      const request = route.request();
      const pathname = new URL(request.url()).pathname.slice(4);
      let response: unknown;
      let status = 200;
      if (pathname === "/settings/board") {
        response = { boards: [board], devices: ["flagship"], board_type: "black" };
      } else if (pathname.startsWith("/v1/boards/")) {
        response = {
          ...board,
          rows: 6,
          cols: 22,
          is_primary: true,
          paused: false,
          schedule_enabled: true,
          drawing: { source: "profile", features: {} },
          next_change_at: null,
          next_page_id: null,
          active_page_id: showing,
        };
      } else if (pathname === `/v1/pages/${kitchenMorning.id}`) {
        response = opened;
      } else if (pathname === "/v1/pages" || pathname === "/pages") {
        response = { pages: [opened, { ...kitchenMorning, id: "evening", name: "Evening news" }], total: 2 };
      } else if (pathname === "/v1/variables") {
        response = {
          variables: { weather: ["temperature", "alert"] },
          max_lengths: { "weather.temperature": 3, "weather.alert": 10 },
          colors: { red: 63, orange: 64, yellow: 65, green: 66, blue: 67, violet: 68, white: 69, black: 70 },
          formatting: {},
        };
      } else if (pathname === "/v1/functions") {
        response = { functions: {} };
      } else if (pathname === "/templates/render" || pathname === "/templates/render/live") {
        const body = request.postDataJSON() as { template: string | string[] };
        const lines = (Array.isArray(body.template) ? body.template : body.template.split("\n")).map((line) =>
          line.replace("{{weather.temperature}}", "72").replace(/\{\{=[^}]*\}\}/, "OK"),
        );
        response = {
          rendered: lines.join("\n"),
          lines,
          line_count: lines.length,
          charset: "vestaboard_v1",
          charset_issues: [],
          ...(pathname.endsWith("/live") && {
            sent_to_board: true,
            board_id: board.id,
            paused: false,
            silenced: false,
          }),
        };
      } else if (pathname === "/templates/validate") {
        response = {
          valid: false,
          rows: 6,
          cols: 22,
          errors: [{ line: 3, column: 22, code: "line_too_long", message: "Needs 25 of 22 columns", max_length: 25 }],
        };
      } else if (pathname === `/pages/${kitchenMorning.id}/draft`) {
        status = 404;
        response = { detail: "No draft" };
      } else if (pathname === `/pages/${kitchenMorning.id}/revisions`) {
        response = { page_id: kitchenMorning.id, revisions, total: revisions.length };
      } else if (pathname.startsWith(`/pages/${kitchenMorning.id}/revisions/`)) {
        const id = pathname.split("/").pop();
        response = { ...revisions.find((revision) => revision.id === id), content: kitchenMorning };
      } else if (pathname === `/pages/${kitchenMorning.id}/sends`) {
        response = {
          page_id: kitchenMorning.id,
          total: 2,
          sends: [
            {
              at: "2026-11-17T15:41:00Z",
              outcome: "sent",
              via: "auto",
              board_id: board.id,
              board_name: board.name,
              count: 1,
            },
            {
              at: "2026-11-17T14:55:00Z",
              outcome: "held",
              via: "show_now",
              board_id: board.id,
              board_name: board.name,
            },
          ],
        };
      } else if (pathname === "/v1/schedules" || pathname === "/schedules") {
        response = {
          schedules: options.notScheduled
            ? []
            : [
                {
                  id: "s1",
                  page_id: kitchenMorning.id,
                  board_id: board.id,
                  start_time: "07:30",
                  end_time: "08:30",
                  day_pattern: "weekdays",
                  enabled: true,
                  created_at: "",
                },
              ],
          total: options.notScheduled ? 0 : 1,
          default_page_id: null,
          enabled: null,
        };
      } else if (pathname === "/schedules/active/page") {
        response = {
          page_id: showing,
          source: "schedule",
          schedule_enabled: true,
          current_time: "07:41",
          current_day: "friday",
          default_page_id: null,
          temporary_override: { active: false },
        };
      } else if (pathname === "/collections" || pathname === "/v1/collections") {
        response = { collections: [], total: 0 };
      } else if (pathname === "/outputs") {
        response = outputs;
      } else if (pathname === "/settings/plugins") {
        response = { transition_plugins_enabled: false, output_plugins_enabled: false, auto_update: false };
      } else if (pathname === "/plugins") {
        response = { plugins: [], total: 0, enabled_count: 0, plugin_system_enabled: true };
      } else if (pathname === "/plugins/registry") {
        response = { entries: [] };
      } else if (pathname === "/silence-status") {
        response = { active: false, holds_blocked_sends: false, held: null };
      } else if (pathname === "/v1/status") {
        response = { running: true, initialized: true, config_summary: {} };
      } else if (pathname === "/panels") {
        response = { panels: [], total: 0 };
      } else if (pathname === "/settings/all") {
        response = { display: { board_animations: "off", board_flap_speed: "standard" } };
      } else if (pathname === "/config") {
        response = { board_type: "black", refresh_interval: 60 };
      } else {
        await route.fulfill({ status: 404, json: { detail: `Unmocked Creator IDE fixture endpoint: ${pathname}` } });
        return;
      }
      await route.fulfill({ status, json: response });
    },
  );
}
