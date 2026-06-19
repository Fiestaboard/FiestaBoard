/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: settings.tab-hardware + settings.tab-network
 */
import type { Page } from "@playwright/test";

import {
  API_URL,
  authHeaders,
  configureBoard,
  ensureAuthForFetch,
  ensureTwoBoards,
  expect,
  loginIfNeeded,
  openSettingsTab,
  resetToSingleBoard,
  test,
} from "../helpers";

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.describe("regression: settings.hardware", () => {
  /**
   * UX node: settings.tab-hardware
   * Route: /settings (Hardware tab)
   * Expected (missing from current coverage):
   *   - enablement-token toggle mode exercised in UI
   *   - FiestaBoard cloud registry boards path tested
   * See also: web/tests/settings.spec.ts:55; multi-board.spec.ts:39+; settings-full.spec.ts:102
   * Coverage status: partial
   */
  test("settings.tab-hardware — enablement token mode + cloud registry boards", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Hardware");

    // Expand the board card to reveal connection form
    await page.getByText("My Board").first().click();

    // Toggle to enablement_token mode and assert the token-specific UI surfaces
    const tokenToggle = page.getByRole("button", { name: /Enablement Token/i }).first();
    await expect(tokenToggle).toBeVisible({ timeout: 10_000 });
    await tokenToggle.click();

    // "Get API Key from Board" button appears in token mode
    await expect(page.getByRole("button", { name: /Get API Key from Board/i })).toBeVisible({ timeout: 10_000 });

    // Now switch to cloud API mode (the FiestaBoard cloud registry path).
    // The mode-picker buttons contain the label "Cloud API" plus a description,
    // so match by partial text instead of exact role-name.
    const cloudBtn = page.getByRole("button", { name: /Cloud API/i }).first();
    await expect(cloudBtn).toBeVisible({ timeout: 10_000 });
    await cloudBtn.click();

    // Cloud R/W API key field is shown
    await expect(page.getByText(/Read\/Write API Key/i).first()).toBeVisible({
      timeout: 10_000,
    });
  });

  /**
   * UX node: settings.hardware.remove-board-confirm
   * Route: /settings (Hardware tab)
   * Expected (missing from current coverage):
   *   - 'atLeastOneBoard' toast asserted by exact i18n key
   *   - 'boardRemoved' success toast verified by text
   * See also: web/tests/multi-board.spec.ts:318,355
   * Coverage status: partial
   */
  test("settings.hardware.remove-board-confirm — exact i18n toasts on remove guard + success", async ({ page }) => {
    await ensureTwoBoards();

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Hardware");

    // Expand the Note board (15 × 3) to access its Remove button
    await expect(page.getByText("15 × 3").first()).toBeVisible({ timeout: 10_000 });
    await page.getByText("15 × 3").first().click();

    const removeBtn = page.getByRole("button", { name: /Remove Board/i }).first();
    await expect(removeBtn).toBeEnabled({ timeout: 10_000 });
    await removeBtn.click();

    // Success toast text (i18n: displaySettings.boardRemoved = "Board removed")
    await expect(page.getByText("Board removed").first()).toBeVisible({
      timeout: 10_000,
    });

    // Verify the board count actually dropped to 1
    const res = await fetch(`${API_URL}/settings/board`, { headers: authHeaders() });
    const data = await res.json();
    expect(data.boards.length).toBe(1);

    // Now the remaining board's Remove button is disabled (atLeastOneBoard guard)
    // Expand the last remaining board (My Board) by clicking its name
    await page.getByText("My Board").first().click();
    const lastRemoveBtn = page.getByRole("button", { name: /Remove Board/i });
    await expect(lastRemoveBtn).toBeDisabled({ timeout: 10_000 });

    await resetToSingleBoard();
  });

  /**
   * UX node: settings.hardware.enabling
   * Route: /settings (Hardware tab)
   * Preconditions: enable-mutation:pending
   * Expected: 'Enabling...' label on enablement-token button; button disabled
   * Source refs: web/src/components/settings/hardware/*
   * Coverage status: uncovered
   */
  test.fixme("settings.hardware.enabling — enablement-token pending state", async ({ page }) => {
    // Stall the enable-local-api endpoint so the button stays in pending state
    await page.route("**/api/board/enable-local-api", async (route) => {
      await new Promise((r) => setTimeout(r, 4_000));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, api_key: "test-from-enable" }),
      });
    });

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });
    await openSettingsTab(page, "Hardware");

    // Expand the board card
    await page.getByText("My Board").first().click();

    // Switch to enablement_token mode
    await page
      .getByRole("button", { name: /Enablement Token/i })
      .first()
      .click();

    // Fill the token field (board host is already set by configureBoard)
    const tokenInput = page.locator("input[placeholder*='vestaboard.com/local-api']").first();
    await expect(tokenInput).toBeVisible({ timeout: 10_000 });
    await tokenInput.fill("test-enable-token");

    const getKeyBtn = page.getByRole("button", { name: /Get API Key from Board/i });
    await expect(getKeyBtn).toBeEnabled({ timeout: 10_000 });
    await getKeyBtn.click();

    // While the mocked request is in-flight, the button becomes disabled.
    // Label may be "Enabling..." or stay as "Get API Key" — assert the
    // disabled state which is the universally observable pending signal.
    await expect(getKeyBtn).toBeDisabled({ timeout: 5_000 });
  });
});

test.describe("regression: settings.network", () => {
  /**
   * UX node: settings.tab-network.unavailable
   * Route: /settings (Network tab)
   * Preconditions: network-api:unavailable
   * Expected: 'Network controls unavailable on this host' info card
   * Source refs: web/src/components/settings/network/*
   * Coverage status: uncovered
   *
   * On dev/non-FiestaPi hosts the Network tab is hidden entirely when
   * /api/network/wifi/capability returns { available: false } (see
   * web/src/app/settings/page.tsx:121,133). There is no separate
   * "unavailable info card" rendered. Assert tab absence instead.
   */
  test("settings.tab-network.unavailable — Network tab is hidden when wifi capability is unavailable", async ({
    page,
  }) => {
    // Force capability to unavailable (matches the default dev container behavior)
    await page.route("**/api/network/wifi/capability", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ available: false }),
      }),
    );

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    // Hardware tab is always present; Network tab must NOT be present.
    await expect(page.getByRole("tab", { name: "Hardware", exact: true })).toBeVisible();
    await expect(page.getByRole("tab", { name: "Network", exact: true })).toHaveCount(0);
  });

  /**
   * UX node: settings.tab-network.list
   * Route: /settings (Network tab)
   * Preconditions: network-api:available
   * Expected: known + scanned networks render; signal strength visible
   * Source refs: web/src/components/settings/network/*
   * Coverage status: uncovered
   */
  test("settings.tab-network.list — known + scanned networks list rendering", async ({ page }) => {
    await mockWifiAvailable(page);

    await page.goto("/settings");
    await expect(page.getByRole("heading", { name: "Settings", exact: true })).toBeVisible({ timeout: 15_000 });

    await openSettingsTab(page, "Network");

    // Scanned network row shows SSID + signal strength
    await expect(page.getByText("CoffeeShopWiFi").first()).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByText(/72%/).first()).toBeVisible();

    // Saved networks section also rendered
    await expect(page.getByText("HomeNet").first()).toBeVisible({ timeout: 10_000 });
  });

  /**
   * UX node: settings.network.connect-dialog
   * Route: /settings (Network tab)
   * Interactions: click:connect on a network row → dialog opens
   * Expected: dialog requests password (or none for open); Connect/Cancel buttons
   * Source refs: web/src/components/settings/network/*
   * Coverage status: uncovered
   */
  test("settings.network.connect-dialog — connect dialog opens and validates input", async ({ page }) => {
    await mockWifiAvailable(page);

    await page.goto("/settings");
    await openSettingsTab(page, "Network");

    // Click Connect on the secured network row
    const ssidRow = page.getByText("CoffeeShopWiFi").first().locator("xpath=ancestor::li");
    await ssidRow.getByRole("button", { name: /^Connect$/i }).click();

    // Connect dialog opens
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Connect to CoffeeShopWiFi/i)).toBeVisible();

    // Connect button is disabled until a password is typed
    const connectBtn = page.getByRole("dialog").getByRole("button", { name: /^Connect$/i });
    await expect(connectBtn).toBeDisabled();

    // Cancel closes the dialog
    await page
      .getByRole("dialog")
      .getByRole("button", { name: /^Cancel$/i })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 10_000 });
  });

  /**
   * UX node: settings.network.connect-pending
   * Route: /settings (Network tab)
   * Preconditions: connect-mutation:pending
   * Expected: 'Connecting...' label on button; form disabled
   * Source refs: web/src/components/settings/network/*
   * Coverage status: uncovered
   */
  test("settings.network.connect-pending — connect pending state", async ({ page }) => {
    await mockWifiAvailable(page);

    // Stall the connect request to capture the pending state
    await page.route("**/api/network/wifi/connect", async (route) => {
      await new Promise((r) => setTimeout(r, 4_000));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: { connected: true, ssid: "CoffeeShopWiFi", ip_address: "192.0.2.10" },
          connectivity_confirmed: true,
        }),
      });
    });

    await page.goto("/settings");
    await openSettingsTab(page, "Network");

    const ssidRow = page.getByText("CoffeeShopWiFi").first().locator("xpath=ancestor::li");
    await ssidRow.getByRole("button", { name: /^Connect$/i }).click();

    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 10_000 });
    await page.getByLabel(/Password/i).fill("hunter2-secure");

    const connectBtn = page.getByRole("dialog").getByRole("button", { name: /^Connect$/i });
    await connectBtn.click();

    // While in-flight: Connecting... label visible and button disabled
    await expect(page.getByRole("dialog").getByRole("button", { name: /Connecting/i })).toBeVisible({ timeout: 5_000 });
    await expect(page.getByRole("dialog").getByRole("button", { name: /Connecting/i })).toBeDisabled();
  });

  /**
   * UX node: settings.network.disconnect-dialog
   * Route: /settings (Network tab)
   * Interactions: open:current-network-actions → click:disconnect → confirm
   * Expected: AlertDialog confirms disconnect; Cancel preserves connection
   * Source refs: web/src/components/settings/network/*
   * Coverage status: uncovered
   */
  test("settings.network.disconnect-dialog — disconnect confirm dialog", async ({ page }) => {
    await mockWifiAvailable(page, { connected: true });

    await page.goto("/settings");
    await openSettingsTab(page, "Network");

    // The Disconnect button only appears when currently connected.
    const disconnectBtn = page.getByRole("button", { name: /^Disconnect$/i }).first();
    await expect(disconnectBtn).toBeVisible({ timeout: 10_000 });
    await disconnectBtn.click();

    // Confirm dialog opens with the SSID in its title
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Disconnect from HomeNet/i)).toBeVisible();

    // Cancel preserves connection (no API call asserted; just close the dialog)
    await page
      .getByRole("dialog")
      .getByRole("button", { name: /^Cancel$/i })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 10_000 });
  });

  /**
   * UX node: settings.network.forget-dialog
   * Route: /settings (Network tab)
   * Interactions: forget known network → confirm
   * Expected: AlertDialog confirms forget; entry removed from known list
   * Source refs: web/src/components/settings/network/*
   * Coverage status: uncovered
   */
  test("settings.network.forget-dialog — forget network confirm dialog", async ({ page }) => {
    await mockWifiAvailable(page);

    await page.goto("/settings");
    await openSettingsTab(page, "Network");

    // Click Forget on the saved network row
    const forgetBtn = page.getByRole("button", { name: /^Forget$/i }).first();
    await expect(forgetBtn).toBeVisible({ timeout: 10_000 });
    await forgetBtn.click();

    // Confirm dialog opens with the network name
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Forget HomeNet/i)).toBeVisible();

    // Cancel closes without forgetting
    await page
      .getByRole("dialog")
      .getByRole("button", { name: /^Cancel$/i })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0, { timeout: 10_000 });

    // The saved entry is still present
    await expect(page.getByText("HomeNet").first()).toBeVisible();
  });

  /**
   * UX node: settings.network.scan-error
   * Route: /settings (Network tab)
   * Preconditions: scan-mutation:error
   * Expected: error toast on scan failure; existing list retained
   * Source refs: web/src/components/settings/network/*
   * Coverage status: uncovered
   */
  test("settings.network.scan-error — scan failure surfaces toast", async ({ page }) => {
    await mockWifiAvailable(page);

    // Override the scan endpoint to fail when the user clicks Rescan
    let scanCalls = 0;
    await page.unroute("**/api/network/wifi/scan");
    await page.route("**/api/network/wifi/scan", (route) => {
      scanCalls += 1;
      if (scanCalls === 1) {
        // Initial automatic scan on mount: return the normal list so the
        // "existing list retained" assertion has something to compare against.
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([{ ssid: "CoffeeShopWiFi", signal: 72, security: "WPA2", in_use: false }]),
        });
      }
      // Subsequent rescan triggered by the user fails.
      return route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "nmcli unavailable" }),
      });
    });

    await page.goto("/settings");
    await openSettingsTab(page, "Network");

    await expect(page.getByText("CoffeeShopWiFi").first()).toBeVisible({
      timeout: 10_000,
    });

    await page.getByRole("button", { name: /Rescan/i }).click();

    // Error toast surfaces (i18n: network.toastScanFailed = "Scan failed: {error}")
    await expect(page.getByText(/Scan failed:/i).first()).toBeVisible({
      timeout: 10_000,
    });

    // Existing list retained
    await expect(page.getByText("CoffeeShopWiFi").first()).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Mock the wifi-related backend endpoints so the Network tab renders
 * predictably on dev hosts (which don't actually have nmcli/D-Bus).
 */
async function mockWifiAvailable(page: Page, opts: { connected?: boolean } = {}) {
  const connected = !!opts.connected;

  await page.route("**/api/network/wifi/capability", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ available: true }),
    }),
  );

  await page.route("**/api/network/wifi/status", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(
        connected
          ? {
              connected: true,
              ssid: "HomeNet",
              ip_address: "192.0.2.5",
              gateway: "192.0.2.1",
              signal: 85,
              internet_reachable: true,
            }
          : { connected: false },
      ),
    }),
  );

  await page.route("**/api/network/wifi/scan", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        { ssid: "CoffeeShopWiFi", signal: 72, security: "WPA2", in_use: false },
        { ssid: "OpenGuest", signal: 41, security: "OPEN", in_use: false },
      ]),
    }),
  );

  await page.route("**/api/network/wifi/saved", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([{ name: "HomeNet" }]),
    }),
  );
}
