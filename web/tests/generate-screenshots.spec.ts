/**
 * Playwright screenshot generator for FiestaBoard documentation.
 *
 * Generates four categories of screenshots in both dark and light modes:
 *   A) Plugin board displays (25 plugins) -- dark only, theme-independent
 *   B) Web UI full-page screenshots (7 pages)
 *   C) Getting-started workflow screenshots (~16 images)
 *   D) Homepage feature icon screenshots (6 cropped images)
 *
 * Run against a running dev container at http://localhost:4420:
 *   npx playwright test --config playwright-screenshots.config.ts
 */

import { expect, type Page, test } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

const API_URL = process.env.BASE_URL ? `${process.env.BASE_URL}/api` : "http://localhost:4420/api";
const BOARD_HOST = process.env.MOCK_BOARD_HOST || "fiestaboard-mock-board";

const DOCS_IMG = path.resolve(__dirname, "../../docs-site/static/img");
const GUIDES_IMG = path.resolve(__dirname, "../../docs-site/static/img/guides");
const FEATURES_IMG = path.resolve(__dirname, "../../docs-site/static/img/features");
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

async function resetToSingleBoard(boardColor: "black" | "white" = "black") {
  await fetch(`${API_URL}/settings/board`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      boards: [
        {
          name: "Living Room",
          device_type: "flagship",
          board_color: boardColor,
          enabled: true,
          api_mode: "local",
          host: BOARD_HOST,
          local_api_key: "test-key",
        },
      ],
    }),
  });
}

async function setBoardColor(color: "black" | "white") {
  await resetToSingleBoard(color);
}

async function createPage(name: string, template: string[]): Promise<string> {
  const res = await fetch(`${API_URL}/pages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, type: "template", template }),
  });
  if (!res.ok) throw new Error(`createPage failed: ${res.status}`);
  const data = await res.json();
  return data.page.id;
}

async function createCollection(name: string, pageIds: string[], intervalSeconds = 30): Promise<string> {
  const res = await fetch(`${API_URL}/collections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name,
      page_ids: pageIds,
      interval_seconds: intervalSeconds,
    }),
  });
  if (!res.ok) throw new Error(`createCollection failed: ${res.status}`);
  const data = await res.json();
  return data.collection.id;
}

async function deleteAllCollections() {
  const res = await fetch(`${API_URL}/collections`);
  if (!res.ok) return;
  const data = await res.json();
  for (const c of data.collections ?? []) {
    await fetch(`${API_URL}/collections/${c.id}`, { method: "DELETE" });
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

async function createSchedule(pageId: string, startTime: string, endTime: string, dayPattern: string): Promise<string> {
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
  // Initial wait for the animation to start and mostly complete
  // (board flip animation is ~5s max: 71 chars × ~70ms each)
  await page.waitForTimeout(6000);

  // Then poll until no tiles are still transitioning
  const maxPoll = 10;
  for (let i = 0; i < maxPoll; i++) {
    const transitioning = await page.locator('[data-is-transitioning="true"]').count();
    if (transitioning === 0) break;
    await page.waitForTimeout(500);
  }
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
async function screenshotElement(page: Page, selector: string, baseFilePath: string) {
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
  await deleteAllCollections();
  await deleteAllPages();
  await disableAllPlugins();
}

// ---------------------------------------------------------------------------
// Vestaboard Template Design Guidelines
//
//  1. CENTER TEXT. Use leading spaces so content sits in the middle of
//     the 22-column board, not flush left. A 12-char string needs ~5
//     leading spaces: floor((22 - len) / 2).
//
//  2. FILL THE ROW. Aim for 18-22 visible characters per row. If
//     natural content is short, restructure or combine data to widen.
//
//  3. COLOR TILES = DECORATION ONLY. Use them for full-row bars and
//     header borders. Never use a single tile as an inline bullet or
//     data indicator mid-text.
//
//  4. NO CANYON FORMAT. Do NOT write "LABEL      VALUE" with a large
//     gap. Keep label and value tight ("LABEL VALUE") or put them on
//     separate centered lines.
//
//  5. TIGHT GRIDS. For tabular data (stocks, transit, aircraft) pack
//     columns with 1-2 space gaps, not 4-8.
//
//  6. SIMPLIFY. Show 2-4 key data points clearly rather than cramming
//     6 metrics in confusing formats.
//
//  7. 22-CHAR LIMIT. Each row is 22 columns. Color tags like `{blue}`
//     consume 1 column (the tile). End tags like `{/blue}` consume 0.
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
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
      "    SAN FRANCISCO",
      "   54 F  PARTLY CLOUDY",
      "   HIGH 62   LOW 48",
      "  WIND 12MPH HUMID 68%",
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
    ],
  },
  {
    id: "stocks",
    name: "Stock Prices",
    template: [
      "{green}AAPL    189.84  +1.2%{/green}",
      "{red}TSLA    248.50  -0.8%{/red}",
      "{green}GOOGL   176.32  +0.5%{/green}",
      "{green}MSFT    415.20  +0.3%{/green}",
      "{red}AMZN    178.90  -0.2%{/red}",
      "{green}NVDA    875.40  +2.1%{/green}",
    ],
  },
  {
    id: "muni",
    name: "SF Muni",
    template: [
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
      "N JUDAH  CHURCH  3 MIN",
      "N JUDAH  CHURCH 12 MIN",
      "7 HAIGHT DUBOCE  8 MIN",
      "38 GEARY POWELL  5 MIN",
      "38 GEARY POWELL 14 MIN",
    ],
  },
  {
    id: "traffic",
    name: "Traffic",
    template: [
      "{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}",
      "    SF TO OAKLAND",
      "",
      " BAY BRIDGE    25 MIN",
      " VIA I-880     32 MIN",
      "{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}",
    ],
  },
  {
    id: "sports_scores",
    name: "Sports Scores",
    template: [
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
      "     NFL SCORES",
      " 49ERS  24  CHIEFS  21",
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
      " COWBOYS 17 EAGLES  31",
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
    ],
  },
  {
    id: "date_time",
    name: "Date & Time",
    template: [
      "{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}",
      "",
      "        MONDAY",
      "    MARCH  9  2026",
      "       10:30 AM",
      "{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}",
    ],
  },
  {
    id: "star_trek_quotes",
    name: "Star Trek Quotes",
    template: [
      "{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}",
      "THE NEEDS OF THE MANY",
      " OUTWEIGH THE NEEDS",
      "      OF THE FEW",
      "",
      "       - MR SPOCK",
    ],
  },
  {
    id: "guest_wifi",
    name: "Guest WiFi",
    template: [
      "{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}",
      "     WIFI NETWORK",
      "    ALOHA-GUEST-5G",
      "",
      "       PASSWORD",
      "      MAHALO2026",
    ],
  },
  {
    id: "nearby_aircraft",
    name: "Nearby Aircraft",
    template: [
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
      "UAL 1532 B738 12000 FT",
      "SWA 445  B737  8200 FT",
      "DAL 892  A321 15400 FT",
      "AAL 210  B789 22100 FT",
      "SKW 5412 E175  6500 FT",
    ],
  },
  {
    id: "disney_parks_times",
    name: "Disney Parks Queue Times",
    template: [
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
      "SPACE MOUNTAIN   45MIN",
      "MATTERHORN BOBS  30MIN",
      "PIRATES CARIBBN  15MIN",
      "HAUNTED MANSION  20MIN",
      "SPLASH MOUNTAIN  60MIN",
    ],
  },
  {
    id: "last_fm",
    name: "Last.fm Now Playing",
    template: [
      "{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}",
      "     NOW PLAYING",
      "  BOHEMIAN RHAPSODY",
      "         QUEEN",
      " A NIGHT AT THE OPERA",
      "{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}",
    ],
  },
  {
    id: "baywheels",
    name: "Bay Wheels",
    template: [
      "{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}",
      "     BAY WHEELS",
      "MARKET + 2ND   8 BIKES",
      "POWELL STATION 9 BIKES",
      "EMBARCADERO   20 BIKES",
      "FERRY BLDG    11 BIKES",
    ],
  },
  {
    id: "home_assistant",
    name: "Home Assistant",
    template: [
      "{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}",
      "     SMART HOME",
      "  LIVING ROOM  72F",
      "  FRONT DOOR  LOCKED",
      "  GARAGE DOOR  CLOSED",
      "  ALARM ARMED 3 LIGHTS",
    ],
  },
  {
    id: "air_fog",
    name: "Air Quality & Fog",
    template: [
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
      "     AIR QUALITY",
      "     AQI 42  GOOD",
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
      "      VISIBILITY",
      "  8.5 MILES  LIGHT FOG",
    ],
  },
  {
    id: "surf",
    name: "Surf Conditions",
    template: [
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
      "   OCEAN BEACH  SF",
      "    4 TO 6 FT WAVES",
      "   14 SEC PERIOD  NW",
      "    WIND 8MPH OFFSHORE",
      "     GOOD CONDITIONS",
    ],
  },
  {
    id: "wsdot",
    name: "WSDOT Ferries",
    template: [
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
      " SEATTLE - BAINBRIDGE",
      "  NEXT DEP  3:30 PM",
      "  VESSEL MV WENATCHEE",
      "  CAR SPACES  45/120",
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
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
      "  {63}  {67}{67}{67}{67}  {66}{66}{66}{66}  {65}{65}{65}{65} ",
      "  {63}  {67}  {67}     {66}  {65}  {65} ",
      "  {63}  {67}  {67}     {66}  {65}  {65} ",
      "  {63}  {67}  {67}  {66}{66}{66}{66}  {65}{65}{65}{65} ",
      "  {63}  {67}  {67}     {66}  {65}  {65} ",
      "  {63}  {67}{67}{67}{67}  {66}{66}{66}{66}  {65}{65}{65}{65} ",
    ],
  },
  {
    id: "stardate",
    name: "Stardate",
    template: [
      "{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}",
      "   USS ENTERPRISE",
      "",
      "       STARDATE",
      "       79145.7",
      "{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}",
    ],
  },
  {
    id: "countdown",
    name: "Countdown",
    template: [
      "{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}",
      "   SUMMER VACATION",
      "",
      "       12 DAYS",
      "    06 HRS  30 MIN",
      "{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}",
    ],
  },
  {
    id: "dad_jokes",
    name: "Dad Jokes",
    template: [
      "{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}",
      "",
      "  WHAT DO YOU CALL A",
      "     FAKE NOODLE?",
      "",
      "     AN IMPASTA!",
    ],
  },
  {
    id: "generic_data",
    name: "Generic Data",
    template: [
      "{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}",
      "    ISS TRACKER",
      "  LAT 32.71  LON 96.80",
      "",
      "    ALTITUDE 420 KM",
      "   SPEED 27600 KM/H",
    ],
  },
  {
    id: "santa_tracker",
    name: "Santa Tracker",
    template: [
      "{63}{66}{63}{66}{63}{66}{63}{66}{63}{66}{63}{66}{63}{66}{63}{66}{63}{66}{63}{66}{63}{66}",
      "    SANTA TRACKER",
      "",
      "   STATUS IN FLIGHT",
      "   NEXT STOP NEW YORK",
      "   GIFTS 2.4 BILLION",
    ],
  },
  {
    id: "spacecraft_launches",
    name: "Spacecraft Launches",
    template: [
      "{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}",
      "     NEXT LAUNCH",
      " FALCON 9  STARLINK",
      " CAPE CANAVERAL  FL",
      "",
      "     T - 02:15:30",
    ],
  },
  {
    id: "white_noise",
    name: "White Noise",
    template: [
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
      "     WHITE NOISE",
      "",
      "   RAIN ON TIN ROOF",
      "   VOL 60%   45 MIN",
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
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
    template: ["GOOD EVENING", "", "SUNSET AT 6:12 PM", "{blue}OCEAN BEACH 4-6 FT{/blue}", "", "MAKE IT SO  - PICARD"],
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
//    Captures both black and white Vestaboard variants for each plugin.
// =========================================================================

test.describe("Plugin Board Display Screenshots", () => {
  test.skip(
    () => !test.info().project.name.includes("dark"),
    "Plugin display screenshots are captured in dark mode only",
  );

  test.beforeAll(async () => {
    await configureBoard();
    await resetToSingleBoard("black");
    await deleteAllSchedules();
    await deleteAllPages();
  });

  for (const plugin of PLUGIN_DISPLAYS) {
    test(`screenshot: ${plugin.id}`, async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem("fiestaboard_wizard_complete", "true");
        localStorage.setItem("theme", "dark");
      });

      const pageId = await createPage(`Screenshot - ${plugin.name}`, plugin.template);
      await setActivePage(pageId);

      const fileName = `${plugin.id.replace(/_/g, "-")}-display.png`;
      const pluginDocsDir = path.join(PLUGINS_DIR, plugin.id, "docs");

      for (const boardColor of ["black", "white"] as const) {
        await setBoardColor(boardColor);

        await page.goto("/");
        await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });

        await waitForBoard(page);

        // White board screenshots need a transparent background so the dark
        // page theme doesn't bleed through the rounded corners.
        if (boardColor === "white") {
          await page.evaluate(() => {
            const s = document.createElement("style");
            s.textContent = `
              html, body, div:not([role="img"]):not([role="img"] *) {
                background: transparent !important;
                background-color: transparent !important;
              }
            `;
            document.head.appendChild(s);
          });
        }

        const screenshotOpts = boardColor === "white" ? { omitBackground: true } : {};

        const boardEl = page.locator('[class*="rounded-lg"][style*="background"]').first();
        if (await boardEl.isVisible()) {
          const docsColorDir = path.join(DOCS_IMG, boardColor);
          ensureDir(docsColorDir);
          await boardEl.screenshot({
            path: path.join(docsColorDir, fileName),
            ...screenshotOpts,
          });

          const pluginColorDir = path.join(pluginDocsDir, boardColor);
          ensureDir(pluginColorDir);
          await boardEl.screenshot({
            path: path.join(pluginColorDir, fileName),
            ...screenshotOpts,
          });

          if (boardColor === "black") {
            ensureDir(DOCS_IMG);
            await boardEl.screenshot({
              path: path.join(DOCS_IMG, fileName),
            });
            ensureDir(pluginDocsDir);
            await boardEl.screenshot({
              path: path.join(pluginDocsDir, fileName),
            });
          }
        }
      }

      await setBoardColor("black");
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
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });
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

    await screenshotPage(page, path.join(DOCS_IMG, "page-editor-wysiwyg.png"));
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

    const collectionId = await createCollection("Work Rotation", [pages.stockTicker, pages.weatherReport], 30);

    await createSchedule(pages.morningDashboard, "06:00", "09:00", "weekdays");
    await createSchedule(`collection:${collectionId}`, "09:00", "17:00", "weekdays");
    await createSchedule(pages.eveningWindDown, "17:00", "22:00", "all");
    await createSchedule(pages.weekendFun, "08:00", "12:00", "weekends");
    await createSchedule(pages.transitHub, "12:00", "17:00", "weekends");

    await setScheduleEnabled(true);

    await page.goto("/schedule");
    await page.waitForTimeout(3000);

    await screenshotPage(page, path.join(DOCS_IMG, "schedule-calendar.png"));
    copyToRootImages("schedule-calendar.png");

    await setScheduleEnabled(false);
    await deleteAllSchedules();
    await deleteAllCollections();
    await deleteAllPages();
  });

  test("integrations page", async ({ page }) => {
    await initPage(page);
    await enableDemoPlugins();

    await page.goto("/integrations");
    await page.waitForTimeout(3000);

    await screenshotPage(page, path.join(DOCS_IMG, "integrations-page.png"));

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

    await screenshotPage(page, path.join(DOCS_IMG, "schedule-list-view.png"));

    await setScheduleEnabled(false);
    await deleteAllSchedules();
    await deleteAllCollections();
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
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });
    await waitForBoard(page);

    await screenshotPage(page, path.join(GUIDES_IMG, "dashboard-running.png"));
    await deleteAllPages();
  });

  test("settings board configuration", async ({ page }) => {
    await initPage(page);

    await page.goto("/settings");
    await page.waitForTimeout(3000);

    await screenshotPage(page, path.join(GUIDES_IMG, "settings-board-config.png"));
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

    await screenshotPage(page, path.join(GUIDES_IMG, "settings-silence-schedule.png"));
  });

  test("integrations full page", async ({ page }) => {
    await initPage(page);
    await enableDemoPlugins();

    await page.goto("/integrations");
    await page.waitForTimeout(3000);

    await screenshotPage(page, path.join(GUIDES_IMG, "integrations-full.png"));

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

    await screenshotPage(page, path.join(GUIDES_IMG, "integrations-plugin-config.png"));

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

    await screenshotPage(page, path.join(GUIDES_IMG, "integrations-plugin-enabled.png"));

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

    await screenshotPage(page, path.join(GUIDES_IMG, "pages-new-button.png"));
    await deleteAllPages();
  });

  test("page editor empty grid", async ({ page }) => {
    await initPage(page);

    await page.goto("/pages/new");
    await page.waitForTimeout(3000);

    await screenshotPage(page, path.join(GUIDES_IMG, "page-editor-grid.png"));
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

    await screenshotPage(page, path.join(GUIDES_IMG, "page-editor-with-variables.png"));

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

    const varPickerBtn = page.getByRole("button", { name: /variable/i }).first();
    if (await varPickerBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await varPickerBtn.click();
      await page.waitForTimeout(1000);
    }

    await screenshotPage(page, path.join(GUIDES_IMG, "page-editor-variable-picker-open.png"));

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

    await screenshotPage(page, path.join(GUIDES_IMG, "page-editor-preview.png"));
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

    await screenshotPage(page, path.join(GUIDES_IMG, "page-editor-colors.png"));
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

    await screenshotPage(page, path.join(GUIDES_IMG, "schedule-mode-toggle.png"));

    await deleteAllSchedules();
    await deleteAllPages();
  });

  test("schedule entry form", async ({ page }) => {
    await initPage(page);

    const pages = await createDemoPages();

    await setScheduleEnabled(true);

    await page.goto("/schedule");
    await page.waitForTimeout(3000);

    const addBtn = page.getByRole("button", { name: /add|new|create/i }).first();
    if (await addBtn.isVisible({ timeout: 3000 }).catch(() => false)) {
      await addBtn.click();
      await page.waitForTimeout(1500);
    }

    await screenshotPage(page, path.join(GUIDES_IMG, "schedule-entry-form.png"));

    await setScheduleEnabled(false);
    await deleteAllSchedules();
    await deleteAllPages();
  });

  test("schedule calendar populated", async ({ page }) => {
    await initPage(page);

    const pages = await createDemoPages();

    const collectionId = await createCollection("Work Rotation", [pages.stockTicker, pages.weatherReport], 30);

    await createSchedule(pages.morningDashboard, "06:00", "09:00", "weekdays");
    await createSchedule(`collection:${collectionId}`, "09:00", "17:00", "weekdays");
    await createSchedule(pages.eveningWindDown, "17:00", "22:00", "all");
    await createSchedule(pages.weekendFun, "08:00", "12:00", "weekends");
    await createSchedule(pages.transitHub, "12:00", "17:00", "weekends");

    await setScheduleEnabled(true);

    await page.goto("/schedule");
    await page.waitForTimeout(3000);

    await screenshotPage(page, path.join(GUIDES_IMG, "schedule-calendar-populated.png"));

    await setScheduleEnabled(false);
    await deleteAllSchedules();
    await deleteAllCollections();
    await deleteAllPages();
  });

  test("start service button", async ({ page }) => {
    await initPage(page);

    await deleteAllPages();
    await setActivePage(null);

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });
    await page.waitForTimeout(3000);

    await screenshotPage(page, path.join(GUIDES_IMG, "start-service-button.png"));
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

    await screenshotElement(page, "main .grid", path.join(FEATURES_IMG, "plugin-architecture.png"));

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

    await screenshotElement(page, ".ProseMirror", path.join(FEATURES_IMG, "wysiwyg-editor.png"));

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
      await screenshotElement(page, ".schedule-calendar-container", path.join(FEATURES_IMG, "schedule-mode.png"));
    } else {
      await page.waitForTimeout(3000);
      await screenshotPage(page, path.join(FEATURES_IMG, "schedule-mode.png"));
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
      await screenshotElement(page, ".animate-card-fade-in >> nth=1", path.join(FEATURES_IMG, "docker-ready.png"));
    } else {
      await screenshotPage(page, path.join(FEATURES_IMG, "docker-ready.png"));
    }
  });

  test("customizable", async ({ page }) => {
    await initPage(page);

    await page.goto("/settings");
    await page.waitForTimeout(3000);

    // Capture the general settings area (first animated card)
    const generalCard = page.locator(".animate-card-fade-in").first();
    if (await generalCard.isVisible({ timeout: 3000 }).catch(() => false)) {
      await screenshotElement(page, ".animate-card-fade-in >> nth=0", path.join(FEATURES_IMG, "customizable.png"));
    } else {
      await screenshotPage(page, path.join(FEATURES_IMG, "customizable.png"));
    }
  });

  test("open-source", async ({ page }) => {
    await initPage(page);

    const pages = await createDemoPages();
    await setActivePage(pages.morningDashboard);

    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({ timeout: 15_000 });
    await waitForBoard(page);

    // Capture the sidebar / navigation area as the "open-source" feature icon
    const sidebar = page.locator("nav").first();
    if (await sidebar.isVisible({ timeout: 3000 }).catch(() => false)) {
      await screenshotElement(page, "nav", path.join(FEATURES_IMG, "open-source.png"));
    } else {
      await screenshotPage(page, path.join(FEATURES_IMG, "open-source.png"));
    }

    await deleteAllPages();
  });
});
