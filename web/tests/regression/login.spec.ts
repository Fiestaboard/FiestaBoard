/**
 * Auto-generated regression stubs from .claude/ux-coverage.json.
 * Subarea: login (loading / setup / sign-in edge states)
 *
 * Note: these tests deliberately exercise the unauthenticated /login flow.
 * The beforeEach intentionally does NOT call loginIfNeeded — the session
 * cookie would otherwise redirect us off /login before we could assert on
 * the pre-auth UI. We still call ensureAuthForFetch + configureBoard so
 * any helper that needs an authenticated fetch (e.g. configureBoard) works,
 * then clearCookies() so the browser is unauthenticated when it visits /login.
 */
import {
  test,
  expect,
  configureBoard,
  ensureAuthForFetch,
} from "../helpers";

test.beforeEach(async ({ context, page }) => {
  await ensureAuthForFetch();
  await configureBoard();
  // Drop any leftover session cookie before each test so /login renders the
  // pre-auth UI instead of bouncing home.
  await context.clearCookies();
  await page.addInitScript(() => {
    localStorage.setItem("fiestaboard_wizard_complete", "true");
  });
});

test.describe("regression: login", () => {
  /**
   * UX node: login.loading
   * Route: /login
   * Preconditions: auth-status-fetch:pending
   * Expected: spinner / 'Checking sign-in status...' placeholder card visible
   * Source refs: web/src/app/login/page.tsx
   * Coverage status: uncovered
   */
  test("login.loading — auth-status pending placeholder card", async ({ page }) => {
    // Stall the /auth/status response so the page stays in its loading branch.
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/auth/status", async (route) => {
      await gate;
      await route.continue();
    });

    await page.goto("/login", { waitUntil: "commit" });

    // Loading card: title + description copy come straight from login.* i18n.
    await expect(
      page.getByRole("heading", { name: "Loading…", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByText("Checking authentication status…"),
    ).toBeVisible();

    // Release the stalled request so test teardown is clean.
    release();
  });

  /**
   * UX node: login.api-unreachable
   * Route: /login
   * Preconditions: api:unreachable
   * Expected: error state 'API unreachable' with retry CTA
   * Source refs: web/src/app/login/page.tsx
   * Coverage status: uncovered
   */
  test("login.api-unreachable — API unreachable error", async ({ page }) => {
    // Force /auth/status to fail so the page enters its statusError branch.
    await page.route("**/api/auth/status", async (route) => {
      await route.fulfill({ status: 503, body: "service unavailable" });
    });

    await page.goto("/login");

    // "Couldn't reach the API" title + the underlying error surfaced in an alert.
    await expect(
      page.getByRole("heading", { name: "Couldn't reach the API", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    // Filter past Next's empty route announcer (also role="alert").
    await expect(
      page.getByRole("alert").filter({ hasText: /Auth status request failed/i }),
    ).toBeVisible();
  });

  /**
   * UX node: login.redirecting
   * Route: /login
   * Preconditions: auth:already-signed-in
   * Expected (missing from current coverage):
   *   - explicit 'redirectingTitle'/'redirectingDescription' copy asserted
   *   - spinner placeholder card render verified
   * See also: web/tests/auth.spec.ts:217,228
   * Coverage status: partial
   */
  test("login.redirecting — explicit redirecting copy and spinner card", async ({ page }) => {
    // Pretend the user is already signed in so the page hits its
    // !status.enabled || status.authenticated branch and renders the
    // redirecting placeholder. We intercept BEFORE the SPA router can
    // actually navigate so the card has time to paint.
    await page.route("**/api/auth/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: true,
          setup_required: false,
          authenticated: true,
          username: "someone",
          mode: "enabled",
          first_run: false,
        }),
      });
    });

    // Point the redirect target at /login itself so router.replace stays on
    // this route — the placeholder card has time to paint and assert against.
    // Without this, router.replace("/") tears the page down before we can see it.
    await page.goto("/login?redirect=%2Flogin");

    // The redirecting card uses the i18n "redirectingTitle" + "redirectingDescription".
    await expect(
      page.getByRole("heading", { name: "Redirecting…", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("One moment…")).toBeVisible();
  });

  /**
   * UX node: login.first-run-picker
   * Route: /login
   * Preconditions: first-run:true
   * Expected: first-run picker offers 'Skip' or 'Create account' paths
   * Source refs: web/src/app/login/page.tsx
   * Coverage status: uncovered
   */
  test("login.first-run-picker — first-run picker offers skip vs create", async ({ page }) => {
    // Mock first-run state without touching real data/auth.json.
    await page.route("**/api/auth/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: true,
          setup_required: true,
          authenticated: false,
          username: null,
          mode: "first_run",
          first_run: true,
        }),
      });
    });

    await page.goto("/login");

    await expect(
      page.getByRole("heading", { name: "Protect this FiestaBoard?", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    // Both picker buttons are present and enabled.
    await expect(
      page.getByRole("button", { name: /Set up a username/i }),
    ).toBeEnabled();
    await expect(
      page.getByRole("button", { name: /Skip — anyone on my network/i }),
    ).toBeEnabled();
  });

  /**
   * UX node: login.skip-pending
   * Route: /login
   * Preconditions: skip-mutation:pending
   * Expected: 'Skipping...' label on Skip button; button disabled
   * Source refs: web/src/app/login/page.tsx
   * Coverage status: uncovered
   */
  test("login.skip-pending — Skip pending state", async ({ page }) => {
    // First-run state so the picker renders.
    await page.route("**/api/auth/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: true,
          setup_required: true,
          authenticated: false,
          username: null,
          mode: "first_run",
          first_run: true,
        }),
      });
    });

    // Stall the skip preference call so the button sits in its pending state.
    let release: () => void = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/auth/preference", async (route) => {
      await gate;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ enabled: false }),
      });
    });

    await page.goto("/login");

    const skipBtn = page.getByRole("button", {
      name: /Skip — anyone on my network/i,
    });
    await expect(skipBtn).toBeVisible({ timeout: 15_000 });
    // The picker card animates in; use a forced click so the layout doesn't
    // cause an "element is not stable" retry loop on slow CI machines.
    await skipBtn.click({ force: true });

    // While the preference mutation is in flight, the button swaps to
    // "Disabling…" and goes disabled. Both buttons in the picker share the
    // submitting flag, so the Enable button is also disabled.
    await expect(page.getByRole("button", { name: /Disabling…/i })).toBeVisible({
      timeout: 5_000,
    });
    await expect(
      page.getByRole("button", { name: /Disabling…/i }),
    ).toBeDisabled();
    await expect(
      page.getByRole("button", { name: /Set up a username/i }),
    ).toBeDisabled();

    release();
  });

  /**
   * UX node: login.setup-submitting
   * Route: /login (setup mode)
   * Preconditions: setup-mutation:pending
   * Expected (missing from current coverage):
   *   - 'creatingButton' pending label asserted
   *   - 409 conflict → sign-in form swap with 'adminExists' error
   * See also: web/tests/auth.spec.ts:100
   * Coverage status: partial
   */
  test("login.setup-submitting — creating pending label + 409 swap to sign-in", async ({
    page,
  }) => {
    // Pretend an admin doesn't exist yet so the setup form renders.
    await page.route("**/api/auth/status", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: true,
          setup_required: true,
          authenticated: false,
          username: null,
          mode: "enabled",
          first_run: false,
        }),
      });
    });

    // Stall the setup POST so we can observe the "Creating…" pending label.
    let releaseSetup: () => void = () => {};
    const setupGate = new Promise<void>((resolve) => {
      releaseSetup = resolve;
    });
    await page.route("**/api/auth/setup", async (route) => {
      await setupGate;
      // Return 409: admin already exists. Page should flip to sign-in mode
      // and surface the "adminExists" message.
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "An administrator account already exists. Please sign in instead.",
        }),
      });
    });

    await page.goto("/login");
    await expect(
      page.getByRole("heading", { name: "Create administrator", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });

    await page.getByLabel("Username").fill("e2e-stub-admin");
    await page.getByLabel("Password", { exact: true }).fill("e2e-password-12345");
    await page.getByLabel("Confirm password").fill("e2e-password-12345");
    await page.getByRole("button", { name: "Create account" }).click();

    // Pending: button label becomes "Creating…" and is disabled.
    const creating = page.getByRole("button", { name: /Creating…/i });
    await expect(creating).toBeVisible({ timeout: 5_000 });
    await expect(creating).toBeDisabled();

    // Release the 409 — the page should swap to sign-in mode and show the alert.
    releaseSetup();

    await expect(
      page.getByRole("heading", { name: "Sign in to FiestaBoard", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
    await expect(
      page.getByRole("alert").filter({ hasText: /administrator account already exists/i }),
    ).toBeVisible({ timeout: 15_000 });
  });

  /**
   * UX node: login.sign-in-submitting
   * Route: /login (sign-in mode)
   * Preconditions: sign-in-mutation:pending
   * Expected (missing from current coverage):
   *   - Loader2 spinner + 'submittingButton' label asserted
   *   - 409 setup-mode swap from sign-in path
   * See also: web/tests/auth.spec.ts:217
   * Coverage status: partial
   */
  test("login.sign-in-submitting — spinner+label and 409 setup swap", async ({ page }) => {
    // CI's main e2e job runs with auth disabled, so /auth/status returns
    // enabled:false and /login redirects to home. Mock it to keep the sign-in
    // form rendered. We also mock /auth/login to avoid hitting the real admin password.
    await page.route("**/api/auth/status", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: true,
          setup_required: false,
          authenticated: false,
          mode: "enabled",
          first_run: false,
        }),
      }),
    );
    let releaseLogin: () => void = () => {};
    const loginGate = new Promise<void>((resolve) => {
      releaseLogin = resolve;
    });
    await page.route("**/api/auth/login", async (route) => {
      await loginGate;
      // Return 409 — page flips back to setup mode (handleLogin's 409 branch).
      await route.fulfill({
        status: 409,
        contentType: "application/json",
        body: JSON.stringify({ detail: "User store empty" }),
      });
    });

    await page.goto("/login");
    await expect(
      page.getByRole("heading", { name: "Sign in to FiestaBoard", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });

    await page.getByLabel("Username").fill("any-user");
    await page.getByLabel("Password", { exact: true }).fill("any-password");
    await page.getByRole("button", { name: "Sign in" }).click();

    // Pending: spinner-bearing button shows "Signing in…" and is disabled.
    const pendingBtn = page.getByRole("button", { name: /Signing in…/i });
    await expect(pendingBtn).toBeVisible({ timeout: 5_000 });
    await expect(pendingBtn).toBeDisabled();

    // Release the 409 — sign-in handler flips status.setup_required=true,
    // swapping the form over to "Create administrator".
    releaseLogin();
    await expect(
      page.getByRole("heading", { name: "Create administrator", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });
  });

  /**
   * UX node: login.sign-in-rate-limited
   * Route: /login (sign-in mode)
   * Preconditions: sign-in:429
   * Expected: rate-limit message visible; submit button disabled; retry timer messaging
   * Source refs: web/src/app/login/page.tsx
   * Coverage status: uncovered
   */
  test("login.sign-in-rate-limited — 429 rate-limit messaging", async ({ page }) => {
    // Mock /auth/status so the sign-in form renders in CI (auth-disabled by default).
    await page.route("**/api/auth/status", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          enabled: true,
          setup_required: false,
          authenticated: false,
          mode: "enabled",
          first_run: false,
        }),
      }),
    );
    // Mock /auth/login to 429 so we don't trip the real rate limiter or
    // submit the admin's real password.
    await page.route("**/api/auth/login", async (route) => {
      await route.fulfill({
        status: 429,
        contentType: "application/json",
        body: JSON.stringify({
          detail: "Too many failed login attempts. Please wait a minute and try again.",
        }),
      });
    });

    await page.goto("/login");
    await expect(
      page.getByRole("heading", { name: "Sign in to FiestaBoard", level: 1 }),
    ).toBeVisible({ timeout: 15_000 });

    await page.getByLabel("Username").fill("any-user");
    await page.getByLabel("Password", { exact: true }).fill("any-password");
    await page.getByRole("button", { name: "Sign in" }).click();

    // Rate-limit alert is surfaced from the 429 detail body.
    await expect(
      page.getByRole("alert").filter({ hasText: /too many failed login attempts/i }),
    ).toBeVisible({ timeout: 15_000 });
    // After the request resolves, the button returns to its idle "Sign in"
    // label (submitting flag clears) but the alert remains visible — which
    // is the user-facing signal that this submission was rejected.
    await expect(
      page.getByRole("button", { name: "Sign in", exact: true }),
    ).toBeVisible();
    // Still on /login.
    await expect(page).toHaveURL(/\/login/);
  });
});
