/**
 * Playwright screenshot generator for the 24 external FiestaBoard plugin repos.
 *
 * For each plugin this generates:
 *   docs/board-display.png          (black board — primary, matched by README.md and manifest.json)
 *   docs/black/board-display.png    (black board variant)
 *   docs/white/board-display.png    (white board variant)
 *
 * The screenshots are written directly into each plugin repo on the local
 * filesystem (~/workspace/fiestaboard-plugin--{name}/...).
 *
 * Run against the running dev container at http://localhost:4420:
 *   npx playwright test --config playwright-external-screenshots.config.ts
 *
 * No plugin installation required — screenshots use hardcoded template strings,
 * the same approach used for all built-in plugin screenshots in
 * generate-screenshots.spec.ts.
 */

import { test, type Page } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";

const API_URL = process.env.BASE_URL
  ? `${process.env.BASE_URL}/api`
  : "http://localhost:4420/api";
const BOARD_HOST = process.env.MOCK_BOARD_HOST || "fiestaboard-mock-board";

// Parent directory that contains all plugin repos
const WORKSPACE_DIR = path.join(os.homedir(), "workspace");

// ---------------------------------------------------------------------------
// Helpers (self-contained — same patterns as generate-screenshots.spec.ts)
// ---------------------------------------------------------------------------

async function configureBoard() {
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

function ensureDir(dir: string) {
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true });
}

async function waitForBoard(page: Page) {
  // Wait for the board flip animation to start and mostly complete
  // (71 tiles × ~70ms = ~5s max)
  await page.waitForTimeout(6000);
  // Poll until no tiles are still transitioning
  const maxPoll = 10;
  for (let i = 0; i < maxPoll; i++) {
    const transitioning = await page
      .locator('[data-is-transitioning="true"]')
      .count();
    if (transitioning === 0) break;
    await page.waitForTimeout(500);
  }
}

// ---------------------------------------------------------------------------
// Plugin display definitions
// ---------------------------------------------------------------------------

interface ExternalPluginDisplay {
  /** Plugin ID (snake_case — matches directory inside the repo) */
  id: string;
  /** Human-readable name */
  name: string;
  /** Repo directory name inside WORKSPACE_DIR */
  repo: string;
  /** 6-row Vestaboard template (≤22 columns each) */
  template: string[];
}

// Color tile shorthand — same numeric codes used in generate-screenshots.spec.ts
//   {63} red/magenta  {64} orange  {65} yellow/green
//   {66} cyan/blue    {67} orange  {68} violet/purple
const EXTERNAL_PLUGIN_DISPLAYS: ExternalPluginDisplay[] = [
  {
    id: "airport_board",
    name: "Airport Board",
    repo: "fiestaboard-plugin--airport-board",
    template: [
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
      "    SFO DEPARTURES",
      "UA 1532  JFK  ON TIME",
      "AA  220  LAX  DELAYED",
      "DL  893  ORD  ON TIME",
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
    ],
  },
  {
    id: "aurora_forecast",
    name: "Aurora Forecast",
    repo: "fiestaboard-plugin--aurora-forecast",
    template: [
      "{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}",
      "   AURORA FORECAST",
      "   KP INDEX   4.3",
      "   ACTIVITY  ACTIVE",
      "  VISIBLE ABOVE 50N",
      "{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}",
    ],
  },
  {
    id: "currency",
    name: "Currency Exchange",
    repo: "fiestaboard-plugin--currency",
    template: [
      "{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}",
      "   CURRENCY RATES",
      "EUR/USD    1.0850",
      "GBP/USD    0.7902",
      "JPY/USD   153.42",
      "CAD/USD    1.3621",
    ],
  },
  {
    id: "earthquake",
    name: "Earthquake Monitor",
    repo: "fiestaboard-plugin--earthquake",
    template: [
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
      "  RECENT EARTHQUAKES",
      "{red}M5.1  RIDGECREST CA{/red}",
      "M3.8  ANCHORAGE  AK",
      "M4.2  HILO  HAWAII",
      "M3.5  SEATTLE    WA",
    ],
  },
  {
    id: "element_of_day",
    name: "Element of the Day",
    repo: "fiestaboard-plugin--element-of-day",
    template: [
      "{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}",
      "  ELEMENT OF THE DAY",
      "     GOLD  AU  79",
      "  PERIOD 6  GROUP 11",
      "  MELT 1064C  19.3G",
      "{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}",
    ],
  },
  {
    id: "hacker_news",
    name: "Hacker News",
    repo: "fiestaboard-plugin--hacker-news",
    template: [
      "{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}",
      "    HACKER NEWS",
      "  OPENAI SHIPS NEW",
      "  REASONING MODEL",
      "  1842 PTS  312 CMTS",
      "{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}",
    ],
  },
  {
    id: "iss_tracker",
    name: "ISS Tracker",
    repo: "fiestaboard-plugin--iss-tracker",
    template: [
      "{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}",
      "     ISS TRACKER",
      "  LAT 51.6  LON -122",
      "  ALTITUDE   408 KM",
      "  SPEED 27600 KM/H",
      "{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}",
    ],
  },
  {
    id: "lightning",
    name: "Lightning Alerts",
    repo: "fiestaboard-plugin--lightning",
    template: [
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
      "  NWS WEATHER ALERT",
      "{red}SEVERE THUNDERSTORM{/red}",
      " CALIFORNIA COASTAL",
      " UNTIL 9:00 PM PDT",
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
    ],
  },
  {
    id: "moon_phase",
    name: "Moon Phase",
    repo: "fiestaboard-plugin--moon-phase",
    template: [
      "{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}",
      "      MOON PHASE",
      "    WAXING GIBBOUS",
      "   ILLUMINATION 78%",
      "  RISE 2:14 PM SET --",
      "{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}",
    ],
  },
  {
    id: "national_day",
    name: "National Day",
    repo: "fiestaboard-plugin--national-day",
    template: [
      "{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}",
      "    NATIONAL DAYS",
      "       MAY 2",
      "  WORLD TUNA DAY",
      "  FIRE ANT AWARENESS",
      "  BABY SHOWER DAY",
    ],
  },
  {
    id: "network_speed",
    name: "Network Speed",
    repo: "fiestaboard-plugin--network-speed",
    template: [
      "{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}",
      "    NETWORK SPEED",
      "   DOWN  482 MBPS",
      "    UP   48 MBPS",
      "   PING    8 MS",
      "{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}",
    ],
  },
  {
    id: "on_this_day",
    name: "On This Day",
    repo: "fiestaboard-plugin--on-this-day",
    template: [
      "{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}",
      "    ON THIS DAY",
      "        1972",
      "   APOLLO 16 LANDS",
      "     ON THE MOON",
      "{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}",
    ],
  },
  {
    id: "pet_facts",
    name: "Pet Facts",
    repo: "fiestaboard-plugin--pet-facts",
    template: [
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
      "      CAT FACTS",
      "",
      " CATS SLEEP 12-16 HRS",
      " EACH DAY ON AVERAGE",
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
    ],
  },
  {
    id: "pihole",
    name: "Pi-hole Stats",
    repo: "fiestaboard-plugin--pihole",
    template: [
      "{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}{65}",
      "    PI-HOLE STATS",
      " QUERIES TODAY 14892",
      " ADS BLOCKED    3241",
      " BLOCK RATE    21.8%",
      " DOMAINS  1.2 MILLION",
    ],
  },
  {
    id: "quote_of_day",
    name: "Quote of the Day",
    repo: "fiestaboard-plugin--quote-of-day",
    template: [
      "{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}{68}",
      "  THE ONLY WAY TO DO",
      " GREAT WORK IS TO LOVE",
      "     WHAT YOU DO",
      "",
      "       STEVE JOBS",
    ],
  },
  {
    id: "reddit_hot",
    name: "Reddit Hot",
    repo: "fiestaboard-plugin--reddit-hot",
    template: [
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
      "   R/TECHNOLOGY",
      "  NEW AI MODEL BEATS",
      "   ALL BENCHMARKS",
      " 14.2K PTS  892 CMTS",
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
    ],
  },
  {
    id: "river_flow",
    name: "River Flow",
    repo: "fiestaboard-plugin--river-flow",
    template: [
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
      "    MERCED RIVER CA",
      "   FLOW   1840 CFS",
      "   GAUGE   8.42 FT",
      "   STATUS  MODERATE",
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
    ],
  },
  {
    id: "solar_activity",
    name: "Solar Activity",
    repo: "fiestaboard-plugin--solar-activity",
    template: [
      "{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}",
      "    SOLAR ACTIVITY",
      "   SUNSPOTS   142",
      "   X-RAY FLUX  B4.2",
      "  SOLAR WIND 428 KMS",
      "{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}",
    ],
  },
  {
    id: "tide_times",
    name: "Tide Times",
    repo: "fiestaboard-plugin--tide-times",
    template: [
      "{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}{67}",
      "   GOLDEN GATE TIDES",
      " 6:12 AM   LOW  0.4",
      "12:41 PM  HIGH  5.2",
      " 6:55 PM   LOW  0.9",
      "11:30 PM  HIGH  4.8",
    ],
  },
  {
    id: "uv_index",
    name: "UV Index",
    repo: "fiestaboard-plugin--uv-index",
    template: [
      "{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}{64}",
      "      UV INDEX",
      "  SAN FRANCISCO  CA",
      "{red}      UV 8  HIGH{/red}",
      "   WEAR SPF 30+",
      "  SEEK SHADE 10-4PM",
    ],
  },
  {
    id: "volcano",
    name: "Volcano Activity",
    repo: "fiestaboard-plugin--volcano",
    template: [
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
      "   VOLCANO ACTIVITY",
      "{red}KILAUEA  HAWAII  RED{/red}",
      "POPOCATEPETL MEX YEL",
      "STROMBOLI ITALY  GRN",
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
    ],
  },
  {
    id: "webhook",
    name: "Webhook",
    repo: "fiestaboard-plugin--webhook",
    template: [
      "{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}",
      "    PUSH MESSAGE",
      "",
      " MEETING IN 5 MINUTES",
      " CONF ROOM B  3RD FL",
      "{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}",
    ],
  },
  {
    id: "wildfire",
    name: "Wildfire Monitor",
    repo: "fiestaboard-plugin--wildfire",
    template: [
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
      "   ACTIVE WILDFIRES",
      "{red}PARK FIRE TEHAMA CA{/red}",
      " 422940 AC  82% CONT",
      "  AQI 148  UNHEALTHY",
      "{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}{63}",
    ],
  },
  {
    id: "word_of_day",
    name: "Word of the Day",
    repo: "fiestaboard-plugin--word-of-day",
    template: [
      "{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}{66}",
      "    WORD OF THE DAY",
      "  EPHEMERAL   ADJ",
      "   EF-EM-ER-AL",
      "  LASTING A VERY",
      "    SHORT TIME",
    ],
  },
];

// =========================================================================
// External Plugin Board Display Screenshots
// =========================================================================

test.describe("External Plugin Board Display Screenshots", () => {
  test.beforeAll(async () => {
    await configureBoard();
    await deleteAllPages();
  });

  for (const plugin of EXTERNAL_PLUGIN_DISPLAYS) {
    test(`screenshot: ${plugin.id}`, async ({ page }) => {
      const repoPath = path.join(WORKSPACE_DIR, plugin.repo);
      if (!fs.existsSync(repoPath)) {
        console.warn(`⚠  Repo not found, skipping: ${repoPath}`);
        return;
      }

      await page.addInitScript(() => {
        localStorage.setItem("fiestaboard_wizard_complete", "true");
        localStorage.setItem("theme", "dark");
      });

      const pageId = await createPage(
        `Screenshot - ${plugin.name}`,
        plugin.template,
      );
      await setActivePage(pageId);

      const pluginDocsDir = path.join(
        repoPath,
        "docs",
      );
      const fileName = "board-display.png";

      for (const boardColor of ["black", "white"] as const) {
        await setBoardColor(boardColor);

        await page.goto("/");
        await page
          .getByRole("heading", { name: "Dashboard" })
          .waitFor({ timeout: 15_000 });

        await waitForBoard(page);

        // For white board screenshots, transparent background prevents dark
        // theme from bleeding through the rounded corners.
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

        const screenshotOpts =
          boardColor === "white" ? { omitBackground: true } : {};

        const boardEl = page
          .locator('[class*="rounded-lg"][style*="background"]')
          .first();

        if (await boardEl.isVisible()) {
          // Variant directory (docs/black/ or docs/white/)
          const colorDir = path.join(pluginDocsDir, boardColor);
          ensureDir(colorDir);
          await boardEl.screenshot({
            path: path.join(colorDir, fileName),
            ...screenshotOpts,
          });

          // Black board = primary screenshot referenced by manifest.json
          if (boardColor === "black") {
            ensureDir(pluginDocsDir);
            await boardEl.screenshot({
              path: path.join(pluginDocsDir, fileName),
            });
            console.log(`  ✓ ${plugin.id} → ${path.join(pluginDocsDir, fileName)}`);
          }
        } else {
          console.warn(`  ⚠ Board element not visible for ${plugin.id} (${boardColor})`);
        }
      }

      // Reset to black board and clean up pages before next test
      await setBoardColor("black");
      await deleteAllPages();
    });
  }
});
