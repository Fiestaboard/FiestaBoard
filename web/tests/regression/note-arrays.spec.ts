/**
 * Note arrays — web (Playwright) regression coverage. [#1180]
 *
 * Covers the genuinely E2E-reachable note-array surface in
 * Settings → Hardware (web/src/components/settings/display-settings.tsx):
 *   1. All 5 note-array presets selectable + persisted (W×H + device_type).
 *      (#1178 already covered "4 side-by-side"; this fills the other four and
 *      re-covers all five via a data-driven loop for completeness.)
 *   2. Custom W×H — a valid 3×2 persists; an out-of-range value is blocked
 *      inline and never persisted.
 *   3. Board-card size indicator (#1175) — width × height + preset name; a
 *      non-preset custom size renders "Custom".
 *   4. Auto-detect (#1172/#1178) — flagship classification (token field hides)
 *      and an inline error from a 422 `detail`. (#1178 covered 2×2 success.)
 *
 * Deliberately NOT covered here (unreachable via a user E2E flow): the
 * variable-size preview seams (#1176) and the fit-to-width / actual-size toggle
 * + horizontal scroll at real dims (#1177). No reachable flow renders a
 * note_array board's preview at real dimensions — the page-builder and chat
 * previews resolve note_array to 1×1 (see page-builder.tsx:125-128). Those are
 * covered by component vitest specs:
 *   - web/src/__tests__/scaled-board-display.test.tsx (fit/actual toggle, scroll)
 *   - web/src/__tests__/*board-display* (seams at variable dims)
 */
import {
  API_URL,
  authHeaders,
  configureBoard,
  ensureAuthForFetch,
  expect,
  loginIfNeeded,
  openSettingsTab,
  resetToSingleBoard,
  test,
} from "../helpers";

// The board type combobox aria-label — displaySettings.deviceTypeAriaLabel
// ("Board type and size"), matched against display-settings.tsx:629.
const TYPE_SELECT_LABEL = "Board type and size";

// Preset labels come straight from messages/en.json displaySettings.presets.*
// and the dimensions from src/lib/board-dimensions.ts NOTE_ARRAY_PRESETS.
// charLabel is the BoardSizeIndicator text: `{rows} × {cols}` (rows = h*3,
// cols = w*15). All five presets except "4 side-by-side" go beyond #1178.
const PRESETS = [
  { label: "2 side-by-side", notesWide: 2, notesTall: 1, charLabel: "3 × 30" },
  { label: "4 side-by-side", notesWide: 4, notesTall: 1, charLabel: "3 × 60" },
  { label: "2 stacked", notesWide: 1, notesTall: 2, charLabel: "6 × 15" },
  { label: "4 stacked", notesWide: 1, notesTall: 4, charLabel: "12 × 15" },
  { label: "2×2 grid", notesWide: 2, notesTall: 2, charLabel: "6 × 30" },
] as const;

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await resetToSingleBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.afterEach(async () => {
  await resetToSingleBoard();
});

/** Navigate to Settings → Hardware and expand the single "My Board" card. */
async function openHardwareAndExpand(page: import("@playwright/test").Page) {
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });
  await openSettingsTab(page, "Hardware");
  // Expand the board card (header text is the board name).
  await page.getByText("My Board").first().click();
}

/** The grouped board type/size combobox inside the expanded board card. */
function typeSelect(page: import("@playwright/test").Page) {
  return page.getByRole("combobox", { name: TYPE_SELECT_LABEL }).first();
}

// ---------------------------------------------------------------------------
// 1. All 5 note-array presets — selectable + persisted W×H + device_type
// ---------------------------------------------------------------------------

test.describe("regression: note-arrays — presets", () => {
  for (const preset of PRESETS) {
    test(`preset "${preset.label}" persists note_array ${preset.notesWide}×${preset.notesTall}`, async ({ page }) => {
      await openHardwareAndExpand(page);

      // Open the grouped Select (Devices + Note arrays) and pick the preset.
      const select = typeSelect(page);
      await expect(select).toBeVisible({ timeout: 5_000 });
      await select.click();
      // Options render by role+name from displaySettings.presets.* (display-settings.tsx:642).
      await page.getByRole("option", { name: preset.label, exact: true }).click();
      await page.waitForTimeout(1_500);

      // Board-card size indicator updates to the char dimensions.
      await expect(page.getByText(preset.charLabel).first()).toBeVisible({ timeout: 5_000 });

      // Persisted via the API.
      const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
      const data = await res.json();
      expect(data.boards[0].device_type).toBe("note_array");
      expect(data.boards[0].notes_wide).toBe(preset.notesWide);
      expect(data.boards[0].notes_tall).toBe(preset.notesTall);
    });
  }
});

// ---------------------------------------------------------------------------
// 2. Custom W×H — valid persists; out-of-range blocked inline (not persisted)
// ---------------------------------------------------------------------------

test.describe("regression: note-arrays — custom W×H", () => {
  test("Custom… with 2 × 3 persists notes_wide:3, notes_tall:2", async ({ page }) => {
    await openHardwareAndExpand(page);

    // Pick "Custom…" (displaySettings.customLabel → display-settings.tsx:645).
    const select = typeSelect(page);
    await select.click();
    await page.getByRole("option", { name: "Custom…", exact: true }).click();
    await page.waitForTimeout(1_000);

    // The W×H number inputs are labelled "Notes wide" / "Notes tall"
    // (displaySettings.notesWideLabel/notesTallLabel → display-settings.tsx:682,694).
    const widthInput = page.getByLabel("Notes wide");
    const heightInput = page.getByLabel("Notes tall");
    await expect(widthInput).toBeVisible({ timeout: 5_000 });

    // The inputs are controlled (value bound to board dims) and validate on
    // change, so set values via fill() which replaces the field contents.
    await widthInput.fill("3");
    await page.waitForTimeout(800);
    await heightInput.fill("2");
    await page.waitForTimeout(1_200);

    const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
    const data = await res.json();
    expect(data.boards[0].device_type).toBe("note_array");
    expect(data.boards[0].notes_wide).toBe(3);
    expect(data.boards[0].notes_tall).toBe(2);
  });

  test("out-of-range custom width (9) is blocked inline and not persisted", async ({ page }) => {
    await openHardwareAndExpand(page);

    const select = typeSelect(page);
    await select.click();
    await page.getByRole("option", { name: "Custom…", exact: true }).click();
    await page.waitForTimeout(1_000);

    // Seed a valid 3×2 first so we have a known persisted baseline.
    const widthInput = page.getByLabel("Notes wide");
    const heightInput = page.getByLabel("Notes tall");
    await widthInput.fill("3");
    await page.waitForTimeout(600);
    await heightInput.fill("2");
    await page.waitForTimeout(1_000);

    // Now enter an out-of-range width (MAX_NOTES_PER_AXIS is 8 → 9 is invalid).
    await widthInput.fill("9");
    await page.waitForTimeout(800);

    // Inline error surfaces (displaySettings.customRangeError, max=8 →
    // "Each dimension must be between 1 and 8." display-settings.tsx:705).
    await expect(page.getByText("Each dimension must be between 1 and 8.")).toBeVisible({ timeout: 5_000 });

    // The invalid value was never persisted — width stays at the last valid 3.
    const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
    const data = await res.json();
    expect(data.boards[0].notes_wide).toBe(3);
    expect(data.boards[0].notes_tall).toBe(2);
  });
});

// ---------------------------------------------------------------------------
// 3. Board-card size indicator (#1175) — width × height + preset / Custom
// ---------------------------------------------------------------------------

test.describe("regression: note-arrays — size indicator", () => {
  test('configured 4 side-by-side board shows "3 × 60 · 4 side-by-side"', async ({ page }) => {
    // Configure the single board as a 4-side-by-side note array directly via API.
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        boards: [
          {
            name: "My Board",
            device_type: "note_array",
            notes_wide: 4,
            notes_tall: 1,
            board_color: "black",
            enabled: true,
            api_mode: "local",
            host: "localhost",
            local_api_key: "test-key",
          },
        ],
      }),
    });

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });
    await openSettingsTab(page, "Hardware");

    // The indicator is a role="img" in the always-visible card header.
    // aria-label = boardSizeIndicator.ariaLabelWithLayout
    // ("{rows} rows by {cols} columns, {layout}") → board-size-indicator.tsx:31.
    const indicator = page.getByRole("img", { name: "3 rows by 60 columns, 4 side-by-side" });
    await expect(indicator).toBeVisible({ timeout: 10_000 });

    // Visible text is `{cols} × {rows} · {preset}` (board-size-indicator.tsx:41-46).
    await expect(indicator).toContainText("3 × 60");
    await expect(indicator).toContainText("4 side-by-side");
  });

  test('non-preset custom size (3×2) shows "Custom" in the indicator', async ({ page }) => {
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        boards: [
          {
            name: "My Board",
            device_type: "note_array",
            notes_wide: 3,
            notes_tall: 2,
            board_color: "black",
            enabled: true,
            api_mode: "local",
            host: "localhost",
            local_api_key: "test-key",
          },
        ],
      }),
    });

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });
    await openSettingsTab(page, "Hardware");

    // 3×2 notes → 6 × 45 chars; no preset matches → boardSizeIndicator.custom ("Custom").
    const indicator = page.getByRole("img", { name: "6 rows by 45 columns, Custom" });
    await expect(indicator).toBeVisible({ timeout: 10_000 });
    await expect(indicator).toContainText("6 × 45");
    await expect(indicator).toContainText("Custom");
  });
});

// ---------------------------------------------------------------------------
// 4. Auto-detect (#1172) — flagship classification + inline 422 error
//    (#1178 already covers the 2×2 note_array success path.)
// ---------------------------------------------------------------------------

test.describe("regression: note-arrays — auto-detect", () => {
  test("detect → flagship switches the Select to Flagship and hides the token field", async ({ page }) => {
    // Start from a note_array so the Cloud API Token field is initially shown.
    await fetch(`${API_URL}/settings/board`, {
      method: "PUT",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        boards: [
          {
            name: "My Board",
            device_type: "note_array",
            notes_wide: 2,
            notes_tall: 1,
            board_color: "black",
            enabled: true,
            api_mode: "local",
            host: "localhost",
            local_api_key: "test-key",
          },
        ],
      }),
    });

    // Mock detect-size to classify the board as a flagship (22×6).
    await page.route("**/settings/board/*/detect-size", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ device_type: "flagship", rows: 6, cols: 22 }),
      });
    });

    await openHardwareAndExpand(page);

    // Token field (displaySettings.noteArrayTokenLabel) is present for note arrays.
    // exact: true — "Cloud API token is required" also renders for tokenless arrays.
    await expect(page.getByText("Cloud API Token", { exact: true })).toBeVisible({ timeout: 5_000 });

    // Click Auto-detect (displaySettings.autoDetect → display-settings.tsx:725).
    await page.getByRole("button", { name: "Auto-detect from board" }).first().click();

    // Header now shows flagship dimensions (6 × 22) and persists flagship.
    await expect(page.getByText("6 × 22").first()).toBeVisible({ timeout: 10_000 });
    // The Cloud API Token field is hidden once the board is no longer a note array.
    await expect(page.getByText("Cloud API Token", { exact: true })).toHaveCount(0, { timeout: 5_000 });

    const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
    const data = await res.json();
    expect(data.boards[0].device_type).toBe("flagship");
  });

  test("detect failure surfaces the 422 detail message inline", async ({ page }) => {
    // Mock detect-size to fail with a FastAPI-style 422 `detail`.
    await page.route("**/settings/board/*/detect-size", async (route) => {
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Board did not return a recognizable size" }),
      });
    });

    await openHardwareAndExpand(page);

    await page.getByRole("button", { name: "Auto-detect from board" }).first().click();

    // fetchApi throws Error(detail); handleAutoDetect stores it in detectError
    // and renders it inline (display-settings.tsx:728-732).
    await expect(page.getByText("Board did not return a recognizable size")).toBeVisible({ timeout: 10_000 });

    // The board type is unchanged (still flagship from resetToSingleBoard).
    const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
    const data = await res.json();
    expect(data.boards[0].device_type).toBe("flagship");
  });
});
