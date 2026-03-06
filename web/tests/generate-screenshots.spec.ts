/**
 * Playwright screenshot generator for FiestaBoard documentation.
 *
 * Generates four categories of screenshots in both dark and light modes:
 *   A) Plugin board displays (19 plugins) -- dark only, theme-independent
 *   B) Web UI full-page screenshots (7 pages)
 *   C) Getting-started workflow screenshots (~16 images)
 *   D) Homepage feature icon screenshots (6 cropped images)
 *
 * Run against a running dev container at http://localhost:4420:
 *   npx playwright test --config playwright-screenshots.config.ts
 */

import { test, expect, type Page } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";

const API_URL = process.env.BASE_URL
  ? `${process.env.BASE_URL}/api`
  : "http://localhost:4420/api";
const BOARD_HOST = process.env.MOCK_BOARD_HOST || "fiestaboard-mock-board";

const DOCS_IMG = path.resolve(__dirname, "../../docs-site/static/img");
const GUIDES_IMG = path.resolve(__dirname, "../../docs-site/static/img/guides");
const FEATURES_IMG = path.resolve(
  __dirname,
  "../../docs-site/static/img/features",
);
const PLUGINS_DIR = path.resolve(__dirname, "../../plugins");
const ROOT_IMG = path.resolve(__dirname, "../../images");

// ---------------------------------------------------------------------------
// Theme helpers
// ---------------------------------------------------------------------------

function currentTheme(): "dark" | "light" {
  const name = test.info().project.name;
  return name.includes("light") ? "light" : "dark";
}

function isDark(): boolean {
  return currentTheme() === "dark";
}

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
          name: "Living Room",
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

async function createCarousel(
  name: string,
  pageIds: string[],
  intervalSeconds = 30,
): Promise<string> {
  const res = await fetch(`${API_URL}/carousels`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      page_ids: pageIds,
      interval_seconds: intervalSeconds,
    }),
  });
  if (!res.ok) throw new Error(`createCarousel failed: ${res.status}`);
  const data = await res.json();
  return data.carousel.id;
}

async function deleteAllCarousels() {
  const res = await fetch(`${API_URL}/carousels`);
  if (!res.ok) return;
  const data = await res.json();
  for (const c of data.carousels ?? []) {
    await fetch(`${API_URL}/carousels/${c.id}`, { method: "DELETE" });
  }
}

async function setActivePage(id: string | null) {
  await fetch(`${API_URL}/settings/active-page`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ page_id: id }),
  });
}

async function deleteAllPages() {
  await setActivePage(null);
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

async function setScheduleEnabled(enabled: boolean) {
  await fetch(`${API_URL}/schedules/enabled`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
}

async function enablePlugin(id: string) {
  await fetch(`${API_URL}/plugins/${id}/enable`, { method: "POST" });
}

async function disablePlugin(id: string) {
  await fetch(`${API_URL}/plugins/${id}/disable`, { method: "POST" });
}

async function disableAllPlugins() {
  const res = await fetch(`${API_URL}/plugins`);
  if (!res.ok) return;
  const data = await res.json();
  for (const p of data.plugins) {
    if (p.enabled) await disablePlugin(p.id);
  }
}

const DEMO_PLUGINS = [
  "weather",
  "date_time",
  "stocks",
  "star_trek_quotes",
  "guest_wifi",
  "muni",
  "surf",
  "sports_scores",
];

async function enableDemoPlugins() {
  for (const id of DEMO_PLUGINS) {
    await enablePlugin(id);
  }
}

async function disableDemoPlugins() {
  for (const id of DEMO_PLUGINS) {
    await disablePlugin(id);
  }
}

/**
 * Set up a Playwright page with the wizard suppressed and
 * the next-themes theme forced via localStorage.
 */
async function initPage(page: Page) {
  const theme = currentTheme();
  await page.addInitScript((t: string) => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
    localStorage.setItem("theme", t);
  }, theme);
}

function ensureDir(dir: string) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

async function waitForBoard(page: Page) {
  await page.waitForTimeout(5000);
}

/**
 * Take a full-page screenshot saved into a theme-specific subdirectory.
 * Dark screenshots are also copied to the default (unthemed) path for
 * backward compatibility with existing documentation references.
 */
async function screenshotPage(page: Page, baseFilePath: string) {
  const theme = currentTheme();
  const dir = path.dirname(baseFilePath);
  const file = path.basename(baseFilePath);
  const themedDir = path.join(dir, theme);
  ensureDir(themedDir);
  const themedPath = path.join(themedDir, file);
  await page.screenshot({ path: themedPath, fullPage: false });

  if (isDark()) {
    ensureDir(dir);
    fs.copyFileSync(themedPath, baseFilePath);
  }
}

/**
 * Take an element-level screenshot saved into a theme-specific subdirectory.
 */
async function screenshotElement(
  page: Page,
  selector: string,
  baseFilePath: string,
) {
  const theme = currentTheme();
  const dir = path.dirname(baseFilePath);
  const file = path.basename(baseFilePath);
  const themedDir = path.join(dir, theme);

  ensureDir(themedDir);
  const themedPath = path.join(themedDir, file);
  const el = page.locator(selector).first();
  await el.screenshot({ path: themedPath });

  if (isDark()) {
    ensureDir(dir);
    fs.copyFileSync(themedPath, baseFilePath);
  }
}

/**
 * Copy a docs-site screenshot to the root images/ directory (for README
 * and DockerHub). Saves themed + default versions.
 */
function copyToRootImages(docsFileName: string, rootFileName?: string) {
  const theme = currentTheme();
  const src = path.join(DOCS_IMG, theme, docsFileName);
  if (!fs.existsSync(src)) return;

  const destDir = path.join(ROOT_IMG, theme);
  ensureDir(destDir);
  fs.copyFileSync(src, path.join(destDir, rootFileName ?? docsFileName));

  if (isDark()) {
    ensureDir(ROOT_IMG);
    fs.copyFileSync(src, path.join(ROOT_IMG, rootFileName ?? docsFileName));
  }
}

/** Reset all transient state so tests start clean. */
async function fullReset() {
  await configureBoard();
  await resetToSingleBoard();
  await deleteAllSchedules();
  await deleteAllCarousels();
  await deleteAllPages();
  await disableAllPlugins();
}

// ---------------------------------------------------------------------------
// Plugin board content definitions (unchanged -- plugin screenshots are
// dark-only and handled in Section A)
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

// ---------------------------------------------------------------------------
// Reusable demo page templates (richer content for a "used app" feel)
// ---------------------------------------------------------------------------

const DEMO_PAGES = {
  morningDashboard: {
    name: "Morning Dashboard",
    template: [
      "THURSDAY MAR 6 2026",
      "{blue}54{/blue} F PARTLY CLOUDY SF",
      "N JUDAH 3 MIN  38 GEARY 8M",
      "{green}AAPL 192.50 +1.4%{/green}",
      "{red}TSLA 245.30  -0.6%{/red}",
      "{green}NVDA 890.15 +2.3%{/green}",
    ],
  },
  weatherReport: {
    name: "Weather Report",
    template: [
      "SAN FRANCISCO",
      "{blue}54{/blue} F {yellow}62{/yellow} F CLOUDY",
      "UV 3   HUMIDITY 68%",
      "WIND 12 MPH  W",
      "",
      "{green}AQI 42 - GOOD{/green}",
    ],
  },
  stockTicker: {
    name: "Stock Ticker",
    template: [
      "{green}AAPL   192.50  +1.4%{/green}",
      "{red}TSLA   245.30  -0.6%{/red}",
      "{green}GOOGL  178.90  +0.5%{/green}",
      "{green}MSFT   420.15  +0.3%{/green}",
      "{red}AMZN   182.40  -0.2%{/red}",
      "{green}NVDA   890.15  +2.3%{/green}",
    ],
  },
  transitHub: {
    name: "Transit Hub",
    template: [
      "{67}{67}{67} SF MUNI {67}{67}{67}",
      "N JUDAH       3 MIN",
      "N JUDAH       12 MIN",
      "7 HAIGHT      8 MIN",
      "38 GEARY      5 MIN",
      "38 GEARY      14 MIN",
    ],
  },
  eveningWindDown: {
    name: "Evening Wind Down",
    template: [
      "GOOD EVENING",
      "",
      "SUNSET AT 6:12 PM",
      "{blue}OCEAN BEACH 4-6 FT{/blue}",
      "",
      "MAKE IT SO  - PICARD",
    ],
  },
  weekendFun: {
    name: "Weekend Fun",
    template: [
      "{63}{63} DISNEYLAND {63}{63}",
      "SPACE MTN      45 MIN",
      "MATTERHORN     30 MIN",
      "PIRATES        15 MIN",
      "HAUNTED MANS   20 MIN",
      "SPLASH MTN     60 MIN",
    ],
  },
};

/** Create all demo pages and return a map of key -> pageId. */
async function createDemoPages(): Promise<Record<string, string>> {
  const ids: Record<string, string> = {};
  for (const [key, def] of Object.entries(DEMO_PAGES)) {
    ids[key] = await createPage(def.name, def.template);
  }
  return ids;
}

// =========================================================================
// A) Plugin Board Display Screenshots  (dark only, skipped for light)
// =========================================================================

test.describe("Plugin Board Display Screenshots", () => {
  test.skip(
    () => !test.info().project.name.includes("dark"),
    "Plugin display screenshots are captured in dark mode only",
  );

  test.beforeAll(async () => {
    await configureBoard();
    await resetToSingleBoard();
    await deleteAllSchedules();
    await deleteAllPages();
  });

  for (const plugin of PLUGIN_DISPLAYS) {
    test(`screenshot: ${plugin.id}`, async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem("fiestaboard_wizard_complete", "true");
        localStorage.setItem("theme", "dark");
      });

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

      const boardEl = page
        .locator('[class*="rounded-lg"][style*="background"]')
        .first();
      if (await boardEl.isVisible()) {
        const pluginDocsDir = path.join(PLUGINS_DIR, plugin.id, "docs");
        const fileName = `${plugin.id.replace(/_/g, "-")}-display.png`;

        await boardEl.screenshot({
          path: path.join(DOCS_IMG, fileName),
        });

        ensureDir(pluginDocsDir);
        await boardEl.screenshot({
          path: path.join(pluginDocsDir, fileName),
        });
      }

      await deleteAllPages();
    });
  }
});

// =========================================================================
// B) Web UI Full-Page Screenshots  (dark + light)
// =========================================================================

test.describe("Web UI Full-Page Screenshots", () => {
  test.beforeAll(async () => {
    await fullReset();
  });

  test("dashboard with active page", async ({ page }) => {
    await initPage(page);

    const pages = await createDemoPages();
    await setActivePage(pages.morningDashboard);

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });
    await waitForBoard(page);

    await screenshotPage(page, path.join(DOCS_IMG, "web-ui-home.png"));
    copyToRootImages("web-ui-home.png");
    await deleteAllPages();
  });

  test("page editor", async ({ page }) => {
    await initPage(page);

    const pageId = await createPage("Weather Report", [
      "SAN FRANCISCO",
      "{blue}54{/blue} F {yellow}62{/yellow} F CLOUDY",
      "UV 3   HUMIDITY 68%",
      "WIND 12 MPH  W",
      "",
      "{green}AQI 42 - GOOD{/green}",
    ]);

    await page.goto(`/pages/edit/${pageId}`);
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(DOCS_IMG, "page-editor-wysiwyg.png"),
    );
    copyToRootImages("page-editor-wysiwyg.png");
    await deleteAllPages();
  });

  test("pages list", async ({ page }) => {
    await initPage(page);
    await createDemoPages();

    await page.goto("/pages");
    await page.waitForTimeout(3000);

    await screenshotPage(page, path.join(DOCS_IMG, "pages-list.png"));
    await deleteAllPages();
  });

  test("schedule page", async ({ page }) => {
    await initPage(page);

    const pages = await createDemoPages();

    const carouselId = await createCarousel(
      "Work Rotation",
      [pages.stockTicker, pages.weatherReport],
      30,
    );

    await createSchedule(pages.morningDashboard, "06:00", "09:00", "weekdays");
    await createSchedule(`carousel:${carouselId}`, "09:00", "17:00", "weekdays");
    await createSchedule(pages.eveningWindDown, "17:00", "22:00", "all");
    await createSchedule(pages.weekendFun, "08:00", "12:00", "weekends");
    await createSchedule(pages.transitHub, "12:00", "17:00", "weekends");

    await setScheduleEnabled(true);

    await page.goto("/schedule");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(DOCS_IMG, "schedule-calendar.png"),
    );
    copyToRootImages("schedule-calendar.png");

    await setScheduleEnabled(false);
    await deleteAllSchedules();
    await deleteAllCarousels();
    await deleteAllPages();
  });

  test("integrations page", async ({ page }) => {
    await initPage(page);
    await enableDemoPlugins();

    await page.goto("/integrations");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(DOCS_IMG, "integrations-page.png"),
    );

    await disableDemoPlugins();
  });

  test("settings page", async ({ page }) => {
    await initPage(page);

    await page.goto("/settings");
    await page.waitForTimeout(3000);

    await screenshotPage(page, path.join(DOCS_IMG, "settings-page.png"));
  });

  test("schedule list view", async ({ page }) => {
    await initPage(page);

    const pages = await createDemoPages();

    await createSchedule(pages.morningDashboard, "06:00", "09:00", "weekdays");
    await createSchedule(pages.weatherReport, "09:00", "17:00", "weekdays");
    await createSchedule(pages.eveningWindDown, "17:00", "22:00", "all");
    await createSchedule(pages.weekendFun, "08:00", "12:00", "weekends");

    await setScheduleEnabled(true);

    await page.goto("/schedule");
    await page.waitForTimeout(3000);

    const listBtn = page.getByRole("button", { name: /list/i });
    if (await listBtn.isVisible({ timeout: 2000 }).catch(() => false)) {
      await listBtn.click();
      await page.waitForTimeout(1000);
    }

    await screenshotPage(
      page,
      path.join(DOCS_IMG, "schedule-list-view.png"),
    );

    await setScheduleEnabled(false);
    await deleteAllSchedules();
    await deleteAllCarousels();
    await deleteAllPages();
  });
});

// =========================================================================
// C) Getting Started & Workflow Screenshots  (dark + light)
// =========================================================================

test.describe("Getting Started Workflow Screenshots", () => {
  test.beforeAll(async () => {
    await fullReset();
  });

  test("dashboard running state", async ({ page }) => {
    await initPage(page);

    const pages = await createDemoPages();
    await setActivePage(pages.morningDashboard);

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
    await initPage(page);

    await page.goto("/settings");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "settings-board-config.png"),
    );
  });

  test("settings silence schedule", async ({ page }) => {
    await initPage(page);

    await page.goto("/settings");
    await page.waitForTimeout(3000);

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
    await initPage(page);
    await enableDemoPlugins();

    await page.goto("/integrations");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "integrations-full.png"),
    );

    await disableDemoPlugins();
  });

  test("integrations plugin config", async ({ page }) => {
    await initPage(page);
    await enablePlugin("weather");

    await page.goto("/integrations");
    await page.waitForTimeout(3000);

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
    await initPage(page);

    await enablePlugin("date_time");
    await enablePlugin("star_trek_quotes");
    await enablePlugin("weather");
    await enablePlugin("stocks");

    await page.goto("/integrations");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "integrations-plugin-enabled.png"),
    );

    await disablePlugin("date_time");
    await disablePlugin("star_trek_quotes");
    await disablePlugin("weather");
    await disablePlugin("stocks");
  });

  test("pages new button", async ({ page }) => {
    await initPage(page);
    await createDemoPages();

    await page.goto("/pages");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "pages-new-button.png"),
    );
    await deleteAllPages();
  });

  test("page editor empty grid", async ({ page }) => {
    await initPage(page);

    await page.goto("/pages/new");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "page-editor-grid.png"),
    );
  });

  test("page editor with variables", async ({ page }) => {
    await initPage(page);

    await enablePlugin("weather");
    await enablePlugin("date_time");

    const pageId = await createPage("Weather Page", [
      "{date_time.date}",
      "SAN FRANCISCO",
      "{weather.temperature} F {weather.condition}",
      "H {weather.high_temp} L {weather.low_temp}",
      "UV {weather.uv_index}",
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
    await initPage(page);

    await enablePlugin("weather");
    await enablePlugin("date_time");
    await enablePlugin("star_trek_quotes");

    await page.goto("/pages/new");
    await page.waitForTimeout(3000);

    const varPickerBtn = page
      .getByRole("button", { name: /variable/i })
      .first();
    if (
      await varPickerBtn.isVisible({ timeout: 3000 }).catch(() => false)
    ) {
      await varPickerBtn.click();
      await page.waitForTimeout(1000);
    }

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "page-editor-variable-picker-open.png"),
    );

    await disablePlugin("weather");
    await disablePlugin("date_time");
    await disablePlugin("star_trek_quotes");
  });

  test("page editor preview", async ({ page }) => {
    await initPage(page);

    const pageId = await createPage("Preview Demo", [
      "THURSDAY MAR 6 2026",
      "{blue}54{/blue} F PARTLY CLOUDY",
      "SAN FRANCISCO  CA",
      "{green}AAPL 192.50 +1.4%{/green}",
      "",
      "HAVE A GREAT DAY!",
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
    await initPage(page);

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
    await initPage(page);

    const pages = await createDemoPages();
    await createSchedule(pages.morningDashboard, "06:00", "09:00", "weekdays");
    await createSchedule(pages.weatherReport, "09:00", "17:00", "weekdays");
    await createSchedule(pages.eveningWindDown, "17:00", "22:00", "all");

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
    await initPage(page);

    const pages = await createDemoPages();

    await setScheduleEnabled(true);

    await page.goto("/schedule");
    await page.waitForTimeout(3000);

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

    await setScheduleEnabled(false);
    await deleteAllSchedules();
    await deleteAllPages();
  });

  test("schedule calendar populated", async ({ page }) => {
    await initPage(page);

    const pages = await createDemoPages();

    const carouselId = await createCarousel(
      "Work Rotation",
      [pages.stockTicker, pages.weatherReport],
      30,
    );

    await createSchedule(pages.morningDashboard, "06:00", "09:00", "weekdays");
    await createSchedule(`carousel:${carouselId}`, "09:00", "17:00", "weekdays");
    await createSchedule(pages.eveningWindDown, "17:00", "22:00", "all");
    await createSchedule(pages.weekendFun, "08:00", "12:00", "weekends");
    await createSchedule(pages.transitHub, "12:00", "17:00", "weekends");

    await setScheduleEnabled(true);

    await page.goto("/schedule");
    await page.waitForTimeout(3000);

    await screenshotPage(
      page,
      path.join(GUIDES_IMG, "schedule-calendar-populated.png"),
    );

    await setScheduleEnabled(false);
    await deleteAllSchedules();
    await deleteAllCarousels();
    await deleteAllPages();
  });

  test("start service button", async ({ page }) => {
    await initPage(page);

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

// =========================================================================
// D) Homepage Feature Icon Screenshots  (dark + light)
//
// These are cropped element-level screenshots used as feature cards on
// the docs-site landing page.
// =========================================================================

test.describe("Homepage Feature Icon Screenshots", () => {
  test.beforeAll(async () => {
    await fullReset();
  });

  test("plugin-architecture", async ({ page }) => {
    await initPage(page);
    await enableDemoPlugins();

    await page.goto("/integrations");
    await page.waitForTimeout(3000);

    await screenshotElement(
      page,
      "main .grid",
      path.join(FEATURES_IMG, "plugin-architecture.png"),
    );

    await disableDemoPlugins();
  });

  test("wysiwyg-editor", async ({ page }) => {
    await initPage(page);

    const pageId = await createPage("Editor Demo", [
      "SAN FRANCISCO",
      "{blue}54{/blue} F {yellow}62{/yellow} F CLOUDY",
      "UV 3   HUMIDITY 68%",
      "WIND 12 MPH  W",
      "",
      "{green}AQI 42 - GOOD{/green}",
    ]);

    await page.goto(`/pages/edit/${pageId}`);
    await page.waitForTimeout(3000);

    await screenshotElement(
      page,
      ".ProseMirror",
      path.join(FEATURES_IMG, "wysiwyg-editor.png"),
    );

    await deleteAllPages();
  });

  test("schedule-mode", async ({ page }) => {
    await initPage(page);

    const pages = await createDemoPages();

    await createSchedule(pages.morningDashboard, "06:00", "09:00", "weekdays");
    await createSchedule(pages.weatherReport, "09:00", "17:00", "weekdays");
    await createSchedule(pages.eveningWindDown, "17:00", "22:00", "all");
    await createSchedule(pages.weekendFun, "08:00", "12:00", "weekends");

    await setScheduleEnabled(true);

    await page.goto("/schedule");

    // The calendar is lazy-loaded; wait for it to render
    const calendarEl = page.locator(".schedule-calendar-container").first();
    const calendarVisible = await calendarEl
      .waitFor({ state: "visible", timeout: 15_000 })
      .then(() => true)
      .catch(() => false);

    if (calendarVisible) {
      await page.waitForTimeout(1000);
      await screenshotElement(
        page,
        ".schedule-calendar-container",
        path.join(FEATURES_IMG, "schedule-mode.png"),
      );
    } else {
      await page.waitForTimeout(3000);
      await screenshotPage(
        page,
        path.join(FEATURES_IMG, "schedule-mode.png"),
      );
    }

    await setScheduleEnabled(false);
    await deleteAllSchedules();
    await deleteAllPages();
  });

  test("docker-ready", async ({ page }) => {
    await initPage(page);

    await page.goto("/settings");
    await page.waitForTimeout(3000);

    // Capture the board connection / display settings area
    const displayCard = page.locator(".animate-card-fade-in").nth(1);
    if (await displayCard.isVisible({ timeout: 3000 }).catch(() => false)) {
      await screenshotElement(
        page,
        ".animate-card-fade-in >> nth=1",
        path.join(FEATURES_IMG, "docker-ready.png"),
      );
    } else {
      await screenshotPage(
        page,
        path.join(FEATURES_IMG, "docker-ready.png"),
      );
    }
  });

  test("customizable", async ({ page }) => {
    await initPage(page);

    await page.goto("/settings");
    await page.waitForTimeout(3000);

    // Capture the general settings area (first animated card)
    const generalCard = page.locator(".animate-card-fade-in").first();
    if (await generalCard.isVisible({ timeout: 3000 }).catch(() => false)) {
      await screenshotElement(
        page,
        ".animate-card-fade-in >> nth=0",
        path.join(FEATURES_IMG, "customizable.png"),
      );
    } else {
      await screenshotPage(
        page,
        path.join(FEATURES_IMG, "customizable.png"),
      );
    }
  });

  test("open-source", async ({ page }) => {
    await initPage(page);

    const pages = await createDemoPages();
    await setActivePage(pages.morningDashboard);

    await page.goto("/");
    await expect(
      page.getByRole("heading", { name: "Dashboard" }),
    ).toBeVisible({ timeout: 15_000 });
    await waitForBoard(page);

    // Capture the sidebar / navigation area as the "open-source" feature icon
    const sidebar = page.locator("nav").first();
    if (await sidebar.isVisible({ timeout: 3000 }).catch(() => false)) {
      await screenshotElement(
        page,
        "nav",
        path.join(FEATURES_IMG, "open-source.png"),
      );
    } else {
      await screenshotPage(
        page,
        path.join(FEATURES_IMG, "open-source.png"),
      );
    }

    await deleteAllPages();
  });
});
