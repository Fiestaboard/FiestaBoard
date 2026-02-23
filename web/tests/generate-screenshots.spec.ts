/**
 * Playwright screenshot generator for FiestaBoard documentation.
 *
 * Generates three categories of screenshots:
 *   A) Plugin board displays (19 plugins)
 *   B) Web UI full-page screenshots (7 pages)
 *   C) Getting-started workflow screenshots (~19 images)
 *
 * Run against a running dev container at http://localhost:4420:
 *   npx playwright test scripts/generate-screenshots.ts --config scripts/playwright-screenshots.config.ts
 */

import { test, expect, type Page } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";

const API_URL = "http://localhost:4420/api";
const BOARD_HOST = process.env.MOCK_BOARD_HOST || "fiestaboard-mock-board";

const DOCS_IMG = path.resolve(__dirname, "../../docs-site/static/img");
const GUIDES_IMG = path.resolve(__dirname, "../../docs-site/static/img/guides");
const PLUGINS_DIR = path.resolve(__dirname, "../../plugins");

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function configureBoard() {
  await fetch(`${API_URL}/config/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      api_mode: "local",
      local_api_key: "test-key",
      host: BOARD_HOST,
    }),
  });
}

async function resetToSingleBoard() {
  await fetch(`${API_URL}/settings/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      boards: [
        {
          name: "My Board",
          device_type: "flagship",
          board_color: "black",
          enabled: true,
          api_mode: "local",
          host: BOARD_HOST,
          local_api_key: "test-key",
        },
      ],
    }),
  });
}

async function createPage(
  name: string,
  template: string[],
): Promise<string> {
  const res = await fetch(`${API_URL}/pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, type: "template", template }),
  });
  if (!res.ok) throw new Error(`createPage failed: ${res.status}`);
  const data = await res.json();
  return data.page.id;
}

async function setActivePage(id: string | null) {
  await fetch(`${API_URL}/settings/active-page`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_id: id }),
  });
}

async function deleteAllPages() {
  const res = await fetch(`${API_URL}/pages`);
  if (!res.ok) return;
  const data = await res.json();
  for (const p of data.pages) {
    await fetch(`${API_URL}/pages/${p.id}`, { method: "DELETE" });
  }
}

async function deleteAllSchedules() {
  const res = await fetch(`${API_URL}/schedules?board_id=*`);
  if (!res.ok) return;
  const data = await res.json();
  for (const s of data.schedules) {
    await fetch(`${API_URL}/schedules/${s.id}`, { method: "DELETE" });
  }
}

async function createSchedule(
  pageId: string,
  startTime: string,
  endTime: string,
  dayPattern: string,
): Promise<string> {
  const res = await fetch(`${API_URL}/schedules`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      page_id: pageId,
      start_time: startTime,
      end_time: endTime,
      day_pattern: dayPattern,
    }),
  });
  if (!res.ok) throw new Error(`createSchedule failed: ${res.status}`);
  const data = await res.json();
  return data.id;
}

async function enablePlugin(id: string) {
  await fetch(`${API_URL}/plugins/${id}/enable`, { method: "POST" });
}

async function disablePlugin(id: string) {
  await fetch(`${API_URL}/plugins/${id}/disable`, { method: "POST" });
}

async function suppressWizard(page: Page) {
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
}

function ensureDir(dir: string) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

async function waitForBoard(page: Page) {
  await page.waitForTimeout(5000);
}

async function screenshotElement(
  page: Page,
  selector: string,
  filePath: string,
) {
  ensureDir(path.dirname(filePath));
  const el = page.locator(selector).first();
  await el.screenshot({ path: filePath });
}

async function screenshotPage(page: Page, filePath: string) {
  ensureDir(path.dirname(filePath));
  await page.screenshot({ path: filePath, fullPage: false });
}

// ---------------------------------------------------------------------------
// Plugin board content definitions
// ---------------------------------------------------------------------------

interface PluginDisplay {
  id: string;
  name: string;
  template: string[];
}

const PLUGIN_DISPLAYS: PluginDisplay[] = [
  {
    id: "weather",
    name: "Weather",
    template: [
      "SAN FRANCISCO",
      "{blue}52{/blue} F {yellow}62{/yellow} F CLOUDY",
      "UV 3   HUMIDITY 68%",
      "WIND 12 MPH  W",
      "",
      "",
    ],
  },
  {
    id: "stocks",
    name: "Stock Prices",
    template: [
      "{green}AAPL   189.84  +1.2%{/green}",
      "{red}TSLA   248.50  -0.8%{/red}",
      "{green}GOOGL 176.32  +0.5%{/green}",
      "{green}MSFT   415.20  +0.3%{/green}",
      "{red}AMZN   178.90  -0.2%{/red}",
      "{green}NVDA   875.40  +2.1%{/green}",
    ],
  },
  {
    id: "muni",
    name: "SF Muni",
    template: [
      "{67}{67}{67} SF MUNI {67}{67}{67}",
      "N JUDAH       3 MIN",
      "N JUDAH       12 MIN",
      "7 HAIGHT      8 MIN",
      "38 GEARY      5 MIN",
      "38 GEARY      14 MIN",
    ],
  },
  {
    id: "traffic",
    name: "Traffic",
    template: [
      "{65}{65} TRAFFIC {65}{65}",
      "",
      "HOME TO WORK",
      "25 MIN VIA US-101",
      "MODERATE TRAFFIC",
      "",
    ],
  },
  {
    id: "sports_scores",
    name: "Sports Scores",
    template: [
      "{63}{63} NFL SCORES {63}{63}",
      "SF 49ERS   24",
      "KC CHIEFS  21",
      "",
      "DAL COWBOYS 17",
      "PHI EAGLES  31",
    ],
  },
  {
    id: "date_time",
    name: "Date & Time",
    template: [
      "",
      "MONDAY",
      "FEBRUARY 23 2026",
      "10:30 AM",
      "",
      "",
    ],
  },
  {
    id: "star_trek_quotes",
    name: "Star Trek Quotes",
    template: [
      "MAKE IT SO",
      "",
      "",
      "",
      "",
      "- JEAN-LUC PICARD",
    ],
  },
  {
    id: "guest_wifi",
    name: "Guest WiFi",
    template: [
      "",
      "WIFI NETWORK",
      "MYNETWORK-GUEST",
      "PASSWORD",
      "WELCOME2024",
      "",
    ],
  },
  {
    id: "nearby_aircraft",
    name: "Nearby Aircraft",
    template: [
      "{67}{67} AIRCRAFT {67}{67}",
      "UAL 1532  B738  12K FT",
      "SWA 445   B737  8K FT",
      "DAL 892   A321  15K FT",
      "AAL 210   B789  22K FT",
      "SKW 5412  E175  6K FT",
    ],
  },
  {
    id: "disney_parks_times",
    name: "Disney Parks Queue Times",
    template: [
      "{63}{63} DISNEYLAND {63}{63}",
      "SPACE MTN      45 MIN",
      "MATTERHORN     30 MIN",
      "PIRATES        15 MIN",
      "HAUNTED MANS   20 MIN",
      "SPLASH MTN     60 MIN",
    ],
  },
  {
    id: "last_fm",
    name: "Last.fm Now Playing",
    template: [
      "{68}{68} NOW PLAYING {68}{68}",
      "",
      "BOHEMIAN RHAPSODY",
      "QUEEN",
      "",
      "A NIGHT AT THE OPERA",
    ],
  },
  {
    id: "baywheels",
    name: "Bay Wheels",
    template: [
      "{66}{66} BAY WHEELS {66}{66}",
      "MARKET + 2ND",
      "  5 EBIKE   3 CLASSIC",
      "POWELL STATION",
      "  2 EBIKE   7 CLASSIC",
      "4 DOCKS AVAILABLE",
    ],
  },
  {
    id: "home_assistant",
    name: "Home Assistant",
    template: [
      "{66}{66} HOME {66}{66}",
      "LIVING ROOM    72 F",
      "FRONT DOOR     LOCKED",
      "GARAGE         CLOSED",
      "LIGHTS         3 ON",
      "ALARM          ARMED",
    ],
  },
  {
    id: "air_fog",
    name: "Air Quality & Fog",
    template: [
      "AIR QUALITY",
      "{green}AQI 42 - GOOD{/green}",
      "",
      "VISIBILITY",
      "{blue}8.5 MILES{/blue}",
      "LIGHT FOG",
    ],
  },
  {
    id: "surf",
    name: "Surf Conditions",
    template: [
      "{blue}{blue} SURF REPORT {blue}{blue}",
      "OCEAN BEACH SF",
      "WAVE HEIGHT  4-6 FT",
      "SWELL PERIOD 14 SEC",
      "WIND  OFFSHORE 8 MPH",
      "{green}GOOD CONDITIONS{/green}",
    ],
  },
  {
    id: "wsdot",
    name: "WSDOT Ferries",
    template: [
      "{67}{67} WA FERRIES {67}{67}",
      "SEATTLE-BAINBRIDGE",
      "NEXT  3:30 PM",
      "MV WENATCHEE",
      "CAR SPOTS  45/120",
      "",
    ],
  },
  {
    id: "sun_art",
    name: "Sun Art",
    template: [
      "{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}",
      "{65}{65}{65}{65}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{65}{65}{65}{65}",
      "{64}{64}{64}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{64}{64}{64}",
      "{64}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{64}",
      "{65}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{65}",
      "{68}{68}{68}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{68}{68}{68}",
    ],
  },
  {
    id: "visual_clock",
    name: "Visual Clock",
    template: [
      "                      ",
      " {63} {63}    {67}{67}    {66}{66}    {65}{65} ",
      " {63} {63} {67}  {67} {66}{66}{66} {65}{65}{65}",
      " {63} {63} {67}  {67}    {66} {65}  {65}",
      " {63} {63} {67}  {67}    {66} {65}  {65}",
      "  {63}     {67}{67}     {66}  {65}{65} ",
    ],
  },
  {
    id: "stardate",
    name: "Stardate",
    template: [
      "",
      "",
      "STARDATE",
      "79145.7",
      "",
      "",
    ],
  },
];

// =========================================================================
// A) Plugin Board Display Screenshots
// =========================================================================

test.describe("Plugin Board Display Screenshots", () => {
  test.beforeAll(async () => {
    await configureBoard();
    await resetToSingleBoard();
    await deleteAllSchedules();
    await deleteAllPages();
  });

  for (const plugin of PLUGIN_DISPLAYS) {
    test(`screenshot: ${plugin.id}`, async ({ page }) => {
      await suppressWizard(page);

      const pageId = await createPage(
        `Screenshot - ${plugin.name}`,
        plugin.template,
      );
      await setActivePage(pageId);

      await page.goto("/");
      await expect(
        page.getByRole("heading", { name: "Dashboard" }),
      ).toBeVisible({ timeout: 15_000 });

      await waitForBoard(page);

      // Screenshot the board display container
      const boardEl = page.locator('[class*="rounded-lg"][style*="background"]').first();
      if (await boardEl.isVisible()) {
        const pluginDocsDir = path.join(PLUGINS_DIR, plugin.id, "docs");
        const fileName = `${plugin.id.replace(/_/g, "-")}-display.png`;

        // Save to docs-site/static/img/
        await boardEl.screenshot({
          path: path.join(DOCS_IMG, fileName),
        });

        // Save to plugins/{id}/docs/
        ensureDir(pluginDocsDir);
        await boardEl.screenshot({
          path: path.join(pluginDocsDir, fileName),
        });
      }

      // Clean up
      await deleteAllPages();
    });
  }
});

// =========================================================================
// B) Web UI Full-Page Screenshots
// =========================================================================

test.describe("Web UI Full-Page Screenshots", () => {
  test.beforeAll(async () => {
    await configureBoard();
    await resetToSingleBoard();
    await deleteAllSchedules();
    await deleteAllPages();
  });

  test("dashboard with active page", async ({ page }) => {
    await suppressWizard(page);

    // Create a visually interesting page for the dashboard
    const pageId = await createPage("Morning Dashboard", [
      "MONDAY FEB 23 2026",
      "{blue}52{/blue} F  SAN FRANCISCO",
      "N JUDAH  3 MIN",
      "{green}AAPL 189.84 +1.2%{/green}",
      "{red}TSLA 248.50  -0.8%{/red}",
      "HAVE A GREAT DAY!",
    ]);
    await setActivePage(pageId);

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });
    await waitForBoard(page);

    await screenshotPage(page, path.join(DOCS_IMG, "web-ui-home.png"));
    await deleteAllPages();
  });

  test("page editor", async ({ page }) => {
    await suppressWizard(page);

    // Create a page to edit
    const pageId = await createPage("Weather Page", [
      "SAN FRANCISCO",
      "{blue}52{/blue} F CLOUDY",
      "UV 3   HUMIDITY 68%",
      "",
      "",
      "",
    ]);

    await page.goto(`/pages/edit/${pageId}`);
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(DOCS_IMG, "page-editor-wysiwyg.png"),
    );
    await deleteAllPages();
  });

  test("pages list", async ({ page }) => {
    await suppressWizard(page);

    // Create several pages for a populated list
    await createPage("Morning Dashboard", [
      "GOOD MORNING!",
      "{blue}52{/blue} F SAN FRANCISCO",
      "N JUDAH  3 MIN",
      "",
      "",
      "",
    ]);
    await createPage("Weather Display", [
      "SAN FRANCISCO",
      "{blue}52{/blue} F CLOUDY",
      "UV 3   HUMIDITY 68%",
      "",
      "",
      "",
    ]);
    await createPage("Stock Ticker", [
      "{green}AAPL 189.84 +1.2%{/green}",
      "{red}TSLA 248.50  -0.8%{/red}",
      "{green}GOOGL 176.32 +0.5%{/green}",
      "",
      "",
      "",
    ]);
    await createPage("Evening Info", [
      "GOOD EVENING!",
      "SUNSET AT 5:45 PM",
      "",
      "",
      "",
      "",
    ]);

    await page.goto("/pages");
    await page.waitForTimeout(3000);

    await screenshotPage(page, path.join(DOCS_IMG, "pages-list.png"));
    await deleteAllPages();
  });

  test("schedule page", async ({ page }) => {
    await suppressWizard(page);

    // Create pages and schedules for a populated calendar
    const morningId = await createPage("Morning Dashboard", [
      "GOOD MORNING!",
      "",
      "",
      "",
      "",
      "",
    ]);
    const weatherId = await createPage("Weather Display", [
      "SAN FRANCISCO",
      "",
      "",
      "",
      "",
      "",
    ]);
    const eveningId = await createPage("Evening Info", [
      "GOOD EVENING!",
      "",
      "",
      "",
      "",
      "",
    ]);

    await createSchedule(morningId, "06:00", "09:00", "weekdays");
    await createSchedule(weatherId, "09:00", "17:00", "weekdays");
    await createSchedule(eveningId, "17:00", "22:00", "all");

    // Enable schedule mode
    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true }),
    });

    await page.goto("/schedule");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(DOCS_IMG, "schedule-calendar.png"),
    );

    // Clean up
    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: false }),
    });
    await deleteAllSchedules();
    await deleteAllPages();
  });

  test("integrations page", async ({ page }) => {
    await suppressWizard(page);

    // Enable a few plugins for visual variety
    await enablePlugin("weather");
    await enablePlugin("date_time");
    await enablePlugin("star_trek_quotes");
    await enablePlugin("guest_wifi");

    await page.goto("/integrations");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(DOCS_IMG, "integrations-page.png"),
    );

    // Disable plugins
    await disablePlugin("weather");
    await disablePlugin("date_time");
    await disablePlugin("star_trek_quotes");
    await disablePlugin("guest_wifi");
  });

  test("settings page", async ({ page }) => {
    await suppressWizard(page);

    await page.goto("/settings");
    await page.waitForTimeout(3000);

    await screenshotPage(page, path.join(DOCS_IMG, "settings-page.png"));
  });

  test("schedule list view", async ({ page }) => {
    await suppressWizard(page);

    const morningId = await createPage("Morning Dashboard", [
      "GOOD MORNING!",
      "",
      "",
      "",
      "",
      "",
    ]);
    const weatherId = await createPage("Weather Display", [
      "WEATHER",
      "",
      "",
      "",
      "",
      "",
    ]);

    await createSchedule(morningId, "06:00", "09:00", "weekdays");
    await createSchedule(weatherId, "09:00", "17:00", "all");

    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true }),
    });

    await page.goto("/schedule");
    await page.waitForTimeout(3000);

    // Try to find and click a list view toggle if it exists
    const listBtn = page.getByRole("button", { name: /list/i });
    if (await listBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await listBtn.click();
      await page.waitForTimeout(1000);
    }

    await screenshotPage(
      page,
      path.join(DOCS_IMG, "schedule-list-view.png"),
    );

    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: false }),
    });
    await deleteAllSchedules();
    await deleteAllPages();
  });
});

// =========================================================================
// C) Getting Started & Workflow Screenshots
// =========================================================================

test.describe("Getting Started Workflow Screenshots", () => {
  test.beforeAll(async () => {
    await configureBoard();
    await resetToSingleBoard();
    await deleteAllSchedules();
    await deleteAllPages();
  });

  test("dashboard running state", async ({ page }) => {
    await suppressWizard(page);

    const pageId = await createPage("Active Page", [
      "MONDAY FEB 23 2026",
      "{blue}52{/blue} F  SAN FRANCISCO",
      "N JUDAH  3 MIN",
      "",
      "",
      "HAVE A GREAT DAY!",
    ]);
    await setActivePage(pageId);

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });
    await waitForBoard(page);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "dashboard-running.png"),
    );
    await deleteAllPages();
  });

  test("settings board configuration", async ({ page }) => {
    await suppressWizard(page);

    await page.goto("/settings");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "settings-board-config.png"),
    );
  });

  test("settings silence schedule", async ({ page }) => {
    await suppressWizard(page);

    await page.goto("/settings");
    await page.waitForTimeout(3000);

    // Scroll to find silence schedule section
    const silenceText = page.getByText(/silence/i).first();
    if (await silenceText.isVisible({ timeout: 3000 }).catch(() => false)) {
      await silenceText.scrollIntoViewIfNeeded();
      await page.waitForTimeout(500);
    }

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "settings-silence-schedule.png"),
    );
  });

  test("integrations full page", async ({ page }) => {
    await suppressWizard(page);

    await enablePlugin("weather");
    await enablePlugin("date_time");
    await enablePlugin("star_trek_quotes");
    await enablePlugin("stocks");

    await page.goto("/integrations");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "integrations-full.png"),
    );

    await disablePlugin("weather");
    await disablePlugin("date_time");
    await disablePlugin("star_trek_quotes");
    await disablePlugin("stocks");
  });

  test("integrations plugin config", async ({ page }) => {
    await suppressWizard(page);

    await enablePlugin("weather");

    await page.goto("/integrations");
    await page.waitForTimeout(3000);

    // Try to click into a plugin's settings
    const weatherCard = page.getByText("Weather").first();
    if (await weatherCard.isVisible({ timeout: 3000 }).catch(() => false)) {
      await weatherCard.click();
      await page.waitForTimeout(1500);
    }

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "integrations-plugin-config.png"),
    );

    await disablePlugin("weather");
  });

  test("integrations plugin enabled state", async ({ page }) => {
    await suppressWizard(page);

    await enablePlugin("date_time");
    await enablePlugin("star_trek_quotes");

    await page.goto("/integrations");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "integrations-plugin-enabled.png"),
    );

    await disablePlugin("date_time");
    await disablePlugin("star_trek_quotes");
  });

  test("pages new button", async ({ page }) => {
    await suppressWizard(page);

    await createPage("Sample Page", [
      "HELLO WORLD",
      "",
      "",
      "",
      "",
      "",
    ]);

    await page.goto("/pages");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "pages-new-button.png"),
    );
    await deleteAllPages();
  });

  test("page editor empty grid", async ({ page }) => {
    await suppressWizard(page);

    await page.goto("/pages/new");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "page-editor-grid.png"),
    );
  });

  test("page editor with variables", async ({ page }) => {
    await suppressWizard(page);

    await enablePlugin("weather");
    await enablePlugin("date_time");

    const pageId = await createPage("Weather Page", [
      "{date_time.date}",
      "SAN FRANCISCO",
      "{weather.temp_f} F {weather.conditions}",
      "H {weather.high_f} L {weather.low_f}",
      "UV {weather.uv}",
      "",
    ]);

    await page.goto(`/pages/edit/${pageId}`);
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "page-editor-with-variables.png"),
    );

    await disablePlugin("weather");
    await disablePlugin("date_time");
    await deleteAllPages();
  });

  test("page editor variable picker", async ({ page }) => {
    await suppressWizard(page);

    await enablePlugin("weather");
    await enablePlugin("date_time");
    await enablePlugin("star_trek_quotes");

    await page.goto("/pages/new");
    await page.waitForTimeout(3000);

    // Look for the variable picker button ({x} icon)
    const varPickerBtn = page
      .getByRole("button", { name: /variable/i })
      .first();
    if (
      await varPickerBtn.isVisible({ timeout: 3000 }).catch(() => false)
    ) {
      await varPickerBtn.click();
      await page.waitForTimeout(1000);

      await screenshotPage(
        page,
        path.join(GUIDES_IMG, "page-editor-variable-picker-open.png"),
      );
    } else {
      // Fallback: screenshot the editor as-is
      await screenshotPage(
        page,
        path.join(GUIDES_IMG, "page-editor-variable-picker-open.png"),
      );
    }

    await disablePlugin("weather");
    await disablePlugin("date_time");
    await disablePlugin("star_trek_quotes");
  });

  test("page editor preview", async ({ page }) => {
    await suppressWizard(page);

    const pageId = await createPage("Preview Demo", [
      "GOOD MORNING!",
      "{blue}52{/blue} F  SAN FRANCISCO",
      "HAVE A GREAT DAY",
      "",
      "",
      "",
    ]);

    await page.goto(`/pages/edit/${pageId}`);
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "page-editor-preview.png"),
    );
    await deleteAllPages();
  });

  test("page editor colors", async ({ page }) => {
    await suppressWizard(page);

    const pageId = await createPage("Color Demo", [
      "{63}{64}{65}{66}{67}{68}{63}{64}{65}{66}{67}{68}{63}{64}{65}{66}{67}{68}{63}{64}{65}{66}",
      "{red}RED TEXT{/red}",
      "{orange}ORANGE TEXT{/orange}",
      "{yellow}YELLOW TEXT{/yellow}",
      "{green}GREEN TEXT{/green}",
      "{blue}BLUE TEXT{/blue}",
    ]);

    await page.goto(`/pages/edit/${pageId}`);
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "page-editor-colors.png"),
    );
    await deleteAllPages();
  });

  test("schedule mode toggle", async ({ page }) => {
    await suppressWizard(page);

    const pageId = await createPage("Scheduled Page", [
      "HELLO",
      "",
      "",
      "",
      "",
      "",
    ]);
    await createSchedule(pageId, "08:00", "17:00", "weekdays");

    await page.goto("/schedule");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "schedule-mode-toggle.png"),
    );

    await deleteAllSchedules();
    await deleteAllPages();
  });

  test("schedule entry form", async ({ page }) => {
    await suppressWizard(page);

    const pageId = await createPage("Morning Page", [
      "GOOD MORNING",
      "",
      "",
      "",
      "",
      "",
    ]);

    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true }),
    });

    await page.goto("/schedule");
    await page.waitForTimeout(3000);

    // Click "Add Schedule" or similar button
    const addBtn = page
      .getByRole("button", { name: /add|new|create/i })
      .first();
    if (await addBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await addBtn.click();
      await page.waitForTimeout(1500);
    }

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "schedule-entry-form.png"),
    );

    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: false }),
    });
    await deleteAllSchedules();
    await deleteAllPages();
  });

  test("schedule calendar populated", async ({ page }) => {
    await suppressWizard(page);

    const morningId = await createPage("Morning Info", [
      "GOOD MORNING",
      "",
      "",
      "",
      "",
      "",
    ]);
    const workId = await createPage("Work Display", [
      "WORK MODE",
      "",
      "",
      "",
      "",
      "",
    ]);
    const eveningId = await createPage("Evening Wind Down", [
      "GOOD EVENING",
      "",
      "",
      "",
      "",
      "",
    ]);

    await createSchedule(morningId, "06:00", "09:00", "weekdays");
    await createSchedule(workId, "09:00", "17:00", "weekdays");
    await createSchedule(eveningId, "17:00", "22:00", "all");

    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: true }),
    });

    await page.goto("/schedule");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "schedule-calendar-populated.png"),
    );

    await fetch(`${API_URL}/schedules/enabled`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled: false }),
    });
    await deleteAllSchedules();
    await deleteAllPages();
  });

  test("start service button", async ({ page }) => {
    await suppressWizard(page);

    await deleteAllPages();
    await setActivePage(null);

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "start-service-button.png"),
    );
  });
});
