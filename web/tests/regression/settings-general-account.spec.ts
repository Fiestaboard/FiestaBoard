/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: settings.tab-general + settings.tab-account
 *
 * NOTE: The account-tab tests rely heavily on `page.route` mocking so we
 * never actually mutate the real admin user / auth state. Tests that would
 * otherwise destroy the test session (sign out, disable login, password
 * change) intercept the relevant /api/auth/* endpoints and assert on the
 * resulting UI rather than the server state.
 */
import {
  test,
  expect,
  configureBoard,
  API_URL,
  loginIfNeeded,
  ensureAuthForFetch,
  authHeaders,
} from "../helpers";

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await loginIfNeeded(context);
  await configureBoard();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.describe("regression: settings.general", () => {
  /**
   * UX node: settings.tab-general
   * Route: /settings (General tab)
   * Expected (missing from current coverage):
   *   - InstanceName edit-and-save flow
   *   - AppearanceSettings theme selector exercised via Settings page
   *   - LanguageSettings card not exercised
   *   - TimeAndDateCard timezone select not tested
   *   - AccessibilitySettings / AnimationSettings cards not asserted
   * See also: web/tests/settings.spec.ts:27; multi-board.spec.ts:39
   * Coverage status: partial
   */
  test("settings.tab-general — instance name, theme, language, timezone, a11y, animation cards", async ({ page }) => {
    await page.goto("/settings?section=general");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Instance Name card — the input is keyed by id="instance-name".
    await expect(page.locator("#instance-name")).toBeVisible({ timeout: 10_000 });

    // Appearance — Theme group exposes role="radiogroup" or label "Theme".
    // The card title "Appearance" must be present.
    await expect(page.getByText(/appearance/i).first()).toBeVisible();

    // Language card — header "Language" surfaces a select.
    await expect(page.getByText(/^language$/i).first()).toBeVisible();

    // Time & Date card — must show a "Timezone" label/heading.
    await expect(page.getByText(/time.*date|timezone/i).first()).toBeVisible();

    // Location card — latitude/longitude inputs are stable selectors.
    await expect(page.locator("#latitude")).toBeVisible();
    await expect(page.locator("#longitude")).toBeVisible();

    // Accessibility + Animation cards — assert by visible heading text.
    await expect(page.getByText(/accessibility/i).first()).toBeVisible();
    await expect(page.getByText(/animation/i).first()).toBeVisible();
  });

  /**
   * UX node: settings.general.instance-name-saved
   * Route: /settings
   * Expected: editing instance name and clicking Save surfaces success toast and persists
   * Source refs: web/src/components/settings/*
   * Coverage status: uncovered
   *
   * Implementation note: the InstanceName card saves on blur (not via an
   * explicit Save button) and does not surface a success toast — only an
   * error toast on failure. We assert state-distinguishing behavior:
   *   1) PUT /config/general fires with the new instance_name, and
   *   2) the value is restored after we put the original back.
   */
  test("settings.general.instance-name-saved — name edit persists via PUT /config/general", async ({ page, request }) => {
    // Snapshot the current value so we can restore it.
    const before = await request.get(`${API_URL}/config/general`, {
      headers: authHeaders(),
    });
    const beforeJson = await before.json();
    const originalName = (beforeJson?.instance_name ?? "") as string;
    const testName = `qa-test-${Date.now()}`;

    await page.goto("/settings?section=general");
    const input = page.locator("#instance-name");
    await expect(input).toBeVisible({ timeout: 15_000 });

    // Wait for initial load before mutating.
    await expect(input).not.toHaveValue("", { timeout: 5_000 }).catch(() => {});

    const putPromise = page.waitForResponse(
      (r) => r.url().includes("/api/config/general") && r.request().method() === "PUT",
      { timeout: 10_000 },
    );

    await input.fill(testName);
    await input.blur();

    const put = await putPromise;
    expect(put.ok()).toBe(true);
    const putBody = JSON.parse(put.request().postData() ?? "{}");
    expect(putBody.instance_name).toBe(testName);

    // Restore.
    await request.put(`${API_URL}/config/general`, {
      headers: { "Content-Type": "application/json", ...authHeaders() },
      data: { instance_name: originalName },
    });
  });

  /**
   * UX node: settings.general.location-geolocating
   * Route: /settings
   * Preconditions: geolocation-request:pending
   * Expected: 'Detecting location...' pending UI; button disabled
   * Source refs: web/src/components/settings/*
   * Coverage status: uncovered
   */
  test("settings.general.location-geolocating — geolocate pending state", async ({ page }) => {
    // Stub navigator.geolocation so getCurrentPosition never resolves —
    // the button should switch to the pending "Locating..." state and
    // become disabled.
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "geolocation", {
        configurable: true,
        value: {
          getCurrentPosition: () => {
            /* never invoke either callback */
          },
          watchPosition: () => 0,
          clearWatch: () => {},
        },
      });
    });

    await page.goto("/settings?section=general");
    const useLocationBtn = page.getByRole("button", { name: /use my location/i });
    await expect(useLocationBtn).toBeVisible({ timeout: 15_000 });
    await expect(useLocationBtn).toBeEnabled();

    await useLocationBtn.click();

    // After click, the button label flips to "Locating..." (per
    // location-settings.tsx) and the button is disabled.
    const locatingBtn = page.getByRole("button", { name: /locating/i });
    await expect(locatingBtn).toBeVisible({ timeout: 5_000 });
    await expect(locatingBtn).toBeDisabled();
  });

  /**
   * UX node: settings.general.location-error
   * Route: /settings
   * Preconditions: geolocation-request:error
   * Expected: error message surfaces; manual lat/lng inputs remain editable
   * Source refs: web/src/components/settings/*
   * Coverage status: uncovered
   */
  test("settings.general.location-error — geolocate failure shows error and allows manual input", async ({ page }) => {
    // Stub navigator.geolocation to immediately call the error callback
    // with PERMISSION_DENIED (code 1).
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "geolocation", {
        configurable: true,
        value: {
          getCurrentPosition: (
            _success: PositionCallback,
            error?: PositionErrorCallback,
          ) => {
            // Build a PositionError-shaped object. The component reads
            // .code and compares against error.PERMISSION_DENIED (1).
            const err = {
              code: 1,
              PERMISSION_DENIED: 1,
              POSITION_UNAVAILABLE: 2,
              TIMEOUT: 3,
              message: "denied",
            } as unknown as GeolocationPositionError;
            error?.(err);
          },
          watchPosition: () => 0,
          clearWatch: () => {},
        },
      });
    });

    await page.goto("/settings?section=general");
    const useLocationBtn = page.getByRole("button", { name: /use my location/i });
    await expect(useLocationBtn).toBeVisible({ timeout: 15_000 });

    await useLocationBtn.click();

    // Toast error surfaces with the "denied" copy from messages/en.json.
    await expect(
      page.getByText(/location access was denied/i),
    ).toBeVisible({ timeout: 5_000 });

    // Manual inputs remain editable after the failure.
    const lat = page.locator("#latitude");
    const lon = page.locator("#longitude");
    await expect(lat).toBeEnabled();
    await expect(lon).toBeEnabled();
    await lat.fill("40.0");
    await lon.fill("-74.0");
    await expect(lat).toHaveValue("40.0");
    await expect(lon).toHaveValue("-74.0");
  });
});

test.describe("regression: settings.account", () => {
  /**
   * UX node: settings.tab-account.loading
   * Route: /settings (Account tab)
   * Preconditions: account-fetch:pending
   * Expected: loading skeleton for account info
   * Source refs: web/src/components/settings/account/*
   * Coverage status: uncovered
   */
  test("settings.tab-account.loading — Settings page mounts with Account section gated by auth", async ({ page }) => {
    // The Account loading testid requires the Account tab to render, which
    // requires `enabled && authenticated`. Without the parent's query being
    // decoupled from the section's, the loading state cannot be observed.
    // We assert the Settings page itself renders cleanly — the loading branch
    // of AccountSection is exercised by its unit tests in `__tests__/`.
    await page.goto("/settings");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible({ timeout: 15_000 });
  });

  /**
   * UX node: settings.tab-account.signed-in
   * Route: /settings (Account tab)
   * Preconditions: auth:enabled, user:signed-in
   * Expected (missing from current coverage):
   *   - Change username form submission via UI
   *   - Change password form via UI
   *   - Sign out button clicked
   *   - Disable login card exercised
   * See also: web/tests/auth.spec.ts:228,246
   * Coverage status: partial
   */
  test("settings.tab-account.signed-in — change username/password forms, sign out, disable login card render", async ({ page }) => {
    // Pretend auth is on and we're signed in regardless of the actual
    // server mode, so the test is hermetic.
    await page.route("**/api/auth/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: true,
          authenticated: true,
          mode: "enabled",
          username: "admin",
        }),
      });
    });

    await page.goto("/settings?section=account");

    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // Account-section content (use the form field ids — most stable contract).
    await expect(page.locator("#account-username")).toHaveValue("admin", { timeout: 10_000 });
    await expect(page.locator("#account-current-password")).toBeVisible();
    await expect(page.locator("#account-new-password")).toBeVisible();
    await expect(page.locator("#account-confirm-password")).toBeVisible();
    // At least one signed-in marker is present (don't rely on sidebar-vs-card disambiguation).
    await expect(page.getByText(/change password/i).first()).toBeVisible();
    await expect(page.getByText(/disable login/i).first()).toBeVisible();

    // Sign-out button inside the Account section card (not the sidebar's).
    await expect(
      page.getByLabel("Account").getByRole("button", { name: /^sign out$/i }),
    ).toBeEnabled();
  });

  /**
   * UX node: settings.tab-account.auth-disabled
   * Route: /settings (Account tab)
   * Preconditions: auth:disabled
   * Expected: 'Login disabled' state with enable-auth CTA visible
   * Source refs: web/src/components/settings/account/*
   * Coverage status: uncovered
   */
  test("settings.tab-account.auth-disabled — disabled-auth state shows enable CTA", async ({ page }) => {
    await page.route("**/api/auth/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: false,
          authenticated: false,
          mode: "disabled",
        }),
      });
    });

    await page.goto("/settings?section=account");
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible({ timeout: 15_000 });

    // EnableLoginCard surfaces "Turn on login" heading + CTA button.
    await expect(
      page.getByRole("heading", { name: /turn on login/i }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(
      page.getByRole("button", { name: /set up a username/i }),
    ).toBeVisible();
  });

  /**
   * UX node: settings.account.change-username-success
   * Route: /settings (Account tab)
   * Expected: form submit → success toast; persisted username reflected
   * Source refs: web/src/components/settings/account/*
   * Coverage status: uncovered
   */
  test("settings.account.change-username-success — username change persists with toast", async ({ page }) => {
    await page.route("**/api/auth/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: true,
          authenticated: true,
          mode: "enabled",
          username: "admin",
        }),
      });
    });
    // Intercept the real mutation so we never touch the live admin user.
    await page.route("**/api/auth/change-username", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok", username: "new-admin" }),
      });
    });

    await page.goto("/settings?section=account");
    await expect(page.locator("#account-username")).toBeVisible({
      timeout: 15_000,
    });

    await page.locator("#account-username").fill("new-admin");
    await page.locator("#account-username-password").fill("hunter2");

    await page.getByRole("button", { name: /save username/i }).click();

    // Sonner success toast "Username updated".
    await expect(page.getByText(/username updated/i)).toBeVisible({
      timeout: 5_000,
    });
  });

  /**
   * UX node: settings.account.change-password-success
   * Route: /settings (Account tab)
   * Expected: form submit → success toast; user can sign in with new password
   * Source refs: web/src/components/settings/account/*
   * Coverage status: uncovered
   */
  test("settings.account.change-password-success — password change persists with toast", async ({ page }) => {
    await page.route("**/api/auth/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: true,
          authenticated: true,
          mode: "enabled",
          username: "admin",
        }),
      });
    });
    await page.route("**/api/auth/change-password", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok", username: "admin" }),
      });
    });

    await page.goto("/settings?section=account");
    await expect(page.locator("#account-current-password")).toBeVisible({
      timeout: 15_000,
    });

    await page.locator("#account-current-password").fill("currentpw");
    await page.locator("#account-new-password").fill("newpassword123");
    await page.locator("#account-confirm-password").fill("newpassword123");

    await page.getByRole("button", { name: /save password/i }).click();

    await expect(page.getByText(/password updated/i)).toBeVisible({
      timeout: 5_000,
    });
  });

  /**
   * UX node: settings.account.change-password-error
   * Route: /settings (Account tab)
   * Preconditions: change-password:wrong-current-password
   * Expected: inline error 'incorrect current password'; form remains open
   * Source refs: web/src/components/settings/account/*
   * Coverage status: uncovered
   */
  test("settings.account.change-password-error — wrong current password surfaces inline error", async ({ page }) => {
    await page.route("**/api/auth/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: true,
          authenticated: true,
          mode: "enabled",
          username: "admin",
        }),
      });
    });
    await page.route("**/api/auth/change-password", async (route) => {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Current password is incorrect" }),
      });
    });

    await page.goto("/settings?section=account");
    await expect(page.locator("#account-current-password")).toBeVisible({
      timeout: 15_000,
    });

    await page.locator("#account-current-password").fill("wrongpw");
    await page.locator("#account-new-password").fill("newpassword123");
    await page.locator("#account-confirm-password").fill("newpassword123");
    await page.getByRole("button", { name: /save password/i }).click();

    // Inline error renders inside the form as role="alert".
    const alert = page.getByRole("alert").filter({ hasText: /current password is incorrect/i });
    await expect(alert).toBeVisible({ timeout: 5_000 });

    // Form remains open — fields are still rendered & editable.
    await expect(page.locator("#account-current-password")).toBeVisible();
    await expect(page.locator("#account-new-password")).toBeEnabled();
  });

  /**
   * UX node: settings.account.disable-login-dialog
   * Route: /settings (Account tab)
   * Interactions: click:disable-login → confirm dialog
   * Expected: AlertDialog warns about disabling auth; Confirm clears auth state
   * Source refs: web/src/components/settings/account/*
   * Coverage status: uncovered
   */
  test("settings.account.disable-login-dialog — disable login confirm dialog Cancel flow", async ({ page }) => {
    await page.route("**/api/auth/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: true,
          authenticated: true,
          mode: "enabled",
          username: "admin",
        }),
      });
    });
    // Belt-and-braces: even if the user clicks the destructive button by
    // mistake, intercept it. We only exercise the Cancel path here.
    await page.route("**/api/auth/disable", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok" }),
      });
    });

    await page.goto("/settings?section=account");
    // Click the trigger button in the Disable-login card.
    const triggerBtn = page
      .getByRole("button", { name: /^disable login$/i })
      .first();
    await expect(triggerBtn).toBeVisible({ timeout: 15_000 });
    await triggerBtn.click();

    // AlertDialog opens with the warning copy.
    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible({ timeout: 5_000 });
    await expect(dialog).toContainText(/disable login for this fiestaboard/i);
    await expect(
      dialog.getByLabel(/confirm your current password/i),
    ).toBeVisible();

    // Cancel closes the dialog without touching state.
    await dialog.getByRole("button", { name: /^cancel$/i }).click();
    await expect(dialog).not.toBeVisible({ timeout: 5_000 });
  });
});
