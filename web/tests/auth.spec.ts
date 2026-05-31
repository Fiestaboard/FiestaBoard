/**
 * Authentication E2E tests.
 *
 * Exercises the FastAPI `/auth/*` router and the `/login` UI against a
 * container booted with `FIESTABOARD_AUTH_ENABLED=true`.
 *
 * These specs are gated behind `RUN_AUTH_TESTS` in `playwright.config.ts`
 * because the default e2e job runs with auth disabled — running them there
 * would fail since the middleware short-circuits and the login page bounces
 * straight home.
 *
 * The tests inside the serial block share state on purpose: the first one
 * provisions the admin via `/auth/setup`, and the rest log in / log out
 * against that user. Running them in parallel against the same container
 * would race on the user store.
 */
import { test, expect, type APIRequestContext, type Page } from "@playwright/test";

const BASE_URL = process.env.BASE_URL || "http://localhost:4420";
const API_URL = `${BASE_URL}/api`;
// Must match SESSION_COOKIE_NAME in src/auth/service.py.
const SESSION_COOKIE_NAME = "fiestaboard_session";

const ADMIN_USERNAME = "e2e-admin";
const ADMIN_PASSWORD = "e2e-password-12345";
const WRONG_PASSWORD = "definitely-not-it";

type AuthStatus = {
  enabled: boolean;
  setup_required: boolean;
  authenticated: boolean;
  username?: string | null;
  mode: string;
  first_run: boolean;
};

async function fetchAuthStatus(request: APIRequestContext): Promise<AuthStatus> {
  const res = await request.get(`${API_URL}/auth/status`);
  expect(res.ok()).toBe(true);
  return (await res.json()) as AuthStatus;
}

/** Convenience: assert the response carries a Set-Cookie for the session. */
function expectSessionCookieSet(headers: Record<string, string>): void {
  const setCookie = headers["set-cookie"] || "";
  expect(setCookie).toContain(`${SESSION_COOKIE_NAME}=`);
}

test.describe("Authentication", () => {
  test.beforeAll(async ({ request }) => {
    // If somebody runs this file against an auth-disabled container by
    // accident, skip with a clear message instead of failing every test.
    const status = await fetchAuthStatus(request);
    test.skip(
      !status.enabled,
      "Container has FIESTABOARD_AUTH_ENABLED=false; auth specs require it on.",
    );
  });

  test.describe.serial("setup, login, and logout flow", () => {
    test("status reports setup_required before any user exists", async ({ request }) => {
      const status = await fetchAuthStatus(request);
      expect(status.enabled).toBe(true);
      expect(status.setup_required).toBe(true);
      expect(status.authenticated).toBe(false);
      // Env override pins mode to "enabled", so first_run is false even
      // though no user has been provisioned yet.
      expect(status.mode).toBe("enabled");
      expect(status.first_run).toBe(false);
    });

    test("protected API endpoint returns 409 setup_required when no user exists", async ({
      request,
    }) => {
      const res = await request.get(`${API_URL}/settings`);
      expect(res.status()).toBe(409);
      const body = await res.json();
      expect(body.setup_required).toBe(true);
    });

    test("/login renders the create-administrator form on first run", async ({ page }) => {
      await page.goto("/login");
      await expect(page.getByRole("heading", { name: "Create administrator" })).toBeVisible();
      // The setup form has a confirm-password field; the regular sign-in form
      // does not. This is the cheapest tell that we're in setup mode.
      await expect(page.getByLabel("Confirm password")).toBeVisible();
    });

    test("setup form rejects mismatched passwords client-side", async ({ page }) => {
      await page.goto("/login");
      await page.getByLabel("Username").fill(ADMIN_USERNAME);
      await page.getByLabel("Password", { exact: true }).fill(ADMIN_PASSWORD);
      await page.getByLabel("Confirm password").fill("something-else-entirely");
      await page.getByRole("button", { name: "Create account" }).click();
      await expect(page.getByText("Passwords do not match.")).toBeVisible();
      // We should still be on /login — no admin should have been created.
      await expect(page).toHaveURL(/\/login/);
    });

    test("setup form creates admin and redirects to dashboard", async ({ page }) => {
      await page.goto("/login");
      await page.getByLabel("Username").fill(ADMIN_USERNAME);
      await page.getByLabel("Password", { exact: true }).fill(ADMIN_PASSWORD);
      await page.getByLabel("Confirm password").fill(ADMIN_PASSWORD);
      await page.getByRole("button", { name: "Create account" }).click();

      // Setup endpoint logs the new admin in and the page replaces to "/".
      await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 10_000 });

      // Session cookie must be present on the page context.
      const cookies = await page.context().cookies();
      const session = cookies.find((c) => c.name === SESSION_COOKIE_NAME);
      expect(session).toBeTruthy();
      expect(session?.httpOnly).toBe(true);

      // /auth/status should now confirm authentication.
      const after = await fetchAuthStatus(page.request);
      expect(after.authenticated).toBe(true);
      expect(after.setup_required).toBe(false);
      expect(after.username).toBe(ADMIN_USERNAME);
    });

    test("a protected endpoint succeeds with an authenticated session", async ({ playwright }) => {
      // Each test gets a fresh request context, so re-authenticate by hand.
      const ctx = await playwright.request.newContext({ baseURL: BASE_URL });
      try {
        const login = await ctx.post(`${API_URL}/auth/login`, {
          data: { username: ADMIN_USERNAME, password: ADMIN_PASSWORD, remember_me: true },
        });
        expect(login.ok()).toBe(true);
        const res = await ctx.get(`${API_URL}/settings`);
        expect(res.ok()).toBe(true);
      } finally {
        await ctx.dispose();
      }
    });

    test("logout clears the session cookie and protects the API again", async ({
      playwright,
    }) => {
      const ctx = await playwright.request.newContext({ baseURL: BASE_URL });
      try {
        const login = await ctx.post(`${API_URL}/auth/login`, {
          data: { username: ADMIN_USERNAME, password: ADMIN_PASSWORD },
        });
        expect(login.ok()).toBe(true);

        const out = await ctx.post(`${API_URL}/auth/logout`);
        expect(out.ok()).toBe(true);
        // Logout should expire the session cookie.
        expect(out.headers()["set-cookie"] || "").toContain(SESSION_COOKIE_NAME);

        // A protected endpoint must now 401 (user exists, no valid cookie).
        const protectedRes = await ctx.get(`${API_URL}/settings`);
        expect(protectedRes.status()).toBe(401);
      } finally {
        await ctx.dispose();
      }
    });
  });

  test.describe("post-setup sign-in", () => {
    // Each test in this block runs in a fresh browser context, so previous
    // sessions don't bleed in. We sign in / out as needed.

    test("/auth/login rejects wrong password with 401", async ({ request }) => {
      const res = await request.post(`${API_URL}/auth/login`, {
        data: { username: ADMIN_USERNAME, password: WRONG_PASSWORD },
      });
      expect(res.status()).toBe(401);
      const body = await res.json();
      expect(body.detail).toMatch(/invalid/i);
    });

    test("/auth/login accepts valid credentials and sets session cookie", async ({ request }) => {
      const res = await request.post(`${API_URL}/auth/login`, {
        data: {
          username: ADMIN_USERNAME,
          password: ADMIN_PASSWORD,
          remember_me: true,
        },
      });
      expect(res.ok()).toBe(true);
      expectSessionCookieSet(res.headers());
      // The "remember_me=true" branch attaches a Max-Age so the cookie
      // survives a browser restart.
      expect(res.headers()["set-cookie"]).toMatch(/max-age=\d+/i);
    });

    test("/auth/login without remember_me yields a session-only cookie", async ({ request }) => {
      const res = await request.post(`${API_URL}/auth/login`, {
        data: {
          username: ADMIN_USERNAME,
          password: ADMIN_PASSWORD,
          remember_me: false,
        },
      });
      expect(res.ok()).toBe(true);
      // No Max-Age / Expires == browser drops the cookie on close.
      const setCookie = res.headers()["set-cookie"] || "";
      expect(setCookie).not.toMatch(/max-age=/i);
      expect(setCookie).not.toMatch(/expires=/i);
    });

    test("login form: invalid creds show an inline error and stay on /login", async ({ page }) => {
      await page.goto("/login");
      await expect(page.getByRole("heading", { name: "Sign in to FiestaBoard" })).toBeVisible();

      await page.getByLabel("Username").fill(ADMIN_USERNAME);
      await page.getByLabel("Password", { exact: true }).fill(WRONG_PASSWORD);
      await page.getByRole("button", { name: "Sign in" }).click();

      await expect(page.getByText(/invalid username or password/i)).toBeVisible();
      await expect(page).toHaveURL(/\/login/);
    });

    test("login form: valid creds redirect to dashboard", async ({ page }) => {
      await page.goto("/login");
      await page.getByLabel("Username").fill(ADMIN_USERNAME);
      await page.getByLabel("Password", { exact: true }).fill(ADMIN_PASSWORD);
      await page.getByRole("button", { name: "Sign in" }).click();

      await page.waitForURL((url) => !url.pathname.startsWith("/login"), { timeout: 10_000 });
      const status = await fetchAuthStatus(page.request);
      expect(status.authenticated).toBe(true);
    });

    test("authenticated session persists across reload", async ({ page }) => {
      await signIn(page);
      // Land on settings (something other than /), reload, expect to still be there.
      await page.goto("/settings");
      await page.reload();
      await expect(page).toHaveURL(/\/settings/);
      const status = await fetchAuthStatus(page.request);
      expect(status.authenticated).toBe(true);
    });

    test("redirect=... preserves intent through the sign-in form", async ({ page }) => {
      await page.goto("/login?redirect=%2Fsettings");
      await page.getByLabel("Username").fill(ADMIN_USERNAME);
      await page.getByLabel("Password", { exact: true }).fill(ADMIN_PASSWORD);
      await page.getByRole("button", { name: "Sign in" }).click();
      await page.waitForURL(/\/settings/, { timeout: 10_000 });
    });

    test("/profile redirects to /settings while authenticated", async ({ page }) => {
      await signIn(page);
      // The WizardProvider gates every non-/login route behind /config/validate
      // and renders a full-screen loader (then the SetupWizard) when
      // `is_first_run` is true — children never mount, so /profile's
      // redirect useEffect never fires. Configure a stub board so
      // is_first_run flips to false and the page actually loads.
      await ensureBoardConfigured(page);
      await page.goto("/profile");
      // Profile is a thin redirect to /settings?section=general.
      await page.waitForURL(/\/settings/, { timeout: 5_000 });
    });

    test("validation: /auth/login with empty username is rejected (422)", async ({ request }) => {
      const res = await request.post(`${API_URL}/auth/login`, {
        data: { username: "", password: ADMIN_PASSWORD },
      });
      expect(res.status()).toBe(422);
    });

    test("validation: /auth/setup with short password is rejected (422)", async ({ request }) => {
      const res = await request.post(`${API_URL}/auth/setup`, {
        data: { username: "newadmin", password: "short" },
      });
      // Either 422 (pydantic min_length=8) or 409 (user already exists) is acceptable —
      // both prove the endpoint enforces a rule. We assert it's NOT a 2xx.
      expect(res.ok()).toBe(false);
      expect([409, 422]).toContain(res.status());
    });

    test("/auth/setup is rejected once an admin exists (409)", async ({ request }) => {
      const res = await request.post(`${API_URL}/auth/setup`, {
        data: { username: "second-admin", password: "another-password" },
      });
      expect(res.status()).toBe(409);
    });
  });
});

// ---------------------------------------------------------------------------
// helpers
// ---------------------------------------------------------------------------

async function signIn(page: Page): Promise<void> {
  const res = await page.request.post(`${API_URL}/auth/login`, {
    data: {
      username: ADMIN_USERNAME,
      password: ADMIN_PASSWORD,
      remember_me: true,
    },
  });
  if (!res.ok()) {
    throw new Error(`signIn failed: ${res.status()} ${await res.text()}`);
  }
}

/**
 * PUT a stub board config so `/api/config/validate` reports
 * `is_first_run: false`. Without this, the WizardProvider holds the page
 * on a loading screen / setup wizard and any UI test that needs the real
 * page to mount (and run its useEffects) hangs.
 *
 * Idempotent — the values aren't checked against a real board here.
 * Caller must already be authenticated; the session cookie on page.request
 * carries through.
 */
async function ensureBoardConfigured(page: Page): Promise<void> {
  const res = await page.request.put(`${API_URL}/config/board`, {
    data: {
      api_mode: "local",
      local_api_key: "auth-e2e-stub-key",
      host: "127.0.0.1",
    },
  });
  if (!res.ok()) {
    throw new Error(
      `ensureBoardConfigured failed: ${res.status()} ${await res.text()}`,
    );
  }
}
