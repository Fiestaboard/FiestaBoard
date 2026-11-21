/**
 * BB-C-25: sign-in, TV activation, password reset and About each show the
 * Fiesta wordmark. They pass axe with colour contrast ON, exempting only the
 * kit's FIESTA_LOGO_WORDMARK_SELECTOR (WCAG 1.4.3's logotype exception).
 */
import { expect, test } from "@playwright/test";
import { injectAxe } from "axe-playwright";

import { checkSetupA11y } from "./setup-a11y";

// About draws no wordmark today; it is audited with contrast on all the same.
const SCREENS = [
  { mode: "login", signedIn: false, wordmark: true, ready: { role: "button" as const, name: "Sign in" } },
  { mode: "activate", signedIn: true, wordmark: true, ready: { role: "button" as const, name: "Continue" } },
  { mode: "reset", signedIn: false, wordmark: true, ready: { role: "heading" as const, name: "Reset password" } },
  {
    mode: "about",
    signedIn: true,
    wordmark: false,
    ready: { role: "dialog" as const, name: "About FiestaBoard" },
  },
];

for (const theme of ["light", "dark"]) {
  for (const { mode, signedIn, wordmark, ready } of SCREENS) {
    test(`${mode} passes axe with only the wordmark exempt from contrast (${theme})`, async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 900 });
      await page.emulateMedia({ reducedMotion: "reduce" });
      // Only the hub API: Vite serves `/src/lib/api/*` modules too.
      await page.route(
        (url) => url.pathname.startsWith("/api/"),
        async (route) => {
          const path = new URL(route.request().url()).pathname;
          if (path.endsWith("/auth/status"))
            await route.fulfill({
              json: {
                enabled: true,
                authenticated: signedIn,
                username: signedIn ? "example" : undefined,
                setup_required: false,
                tv_sign_in: { enabled: true },
              },
            });
          else if (path.endsWith("/auth/sessions/context"))
            await route.fulfill({ json: { csrf_token: "test_nonce", expires_in: 600 } });
          else await route.fulfill({ status: 404, json: {} });
        },
      );
      await page.goto(`/tests/layout/setup.html?mode=${mode}&theme=${theme}`);
      await expect(page.getByRole(ready.role, { name: ready.name, exact: true }).first()).toBeVisible();
      if (wordmark) await expect(page.locator(".logo-fiesta-text").first()).toBeVisible();
      await injectAxe(page);
      await checkSetupA11y(page);
    });
  }
}
