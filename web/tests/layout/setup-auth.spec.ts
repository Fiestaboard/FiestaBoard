import { expect, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

const shots = process.env.WEB212_SHOTS ?? "test-results/web212-shots";
for (const width of [390, 768, 1280]) {
  for (const theme of ["light", "dark"]) {
    test(`TV consent and password recovery ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.route("**/api/auth/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path === "/api/auth/status")
          await route.fulfill({
            json: {
              enabled: true,
              authenticated: true,
              username: "example",
              setup_required: false,
              tv_sign_in: { enabled: true },
            },
          });
        else if (path === "/api/auth/sessions/context")
          await route.fulfill({ json: { csrf_token: "test_nonce", expires_in: 600 } });
        else if (path === "/api/auth/device/inspect")
          await route.fulfill({
            json: {
              user_code: "BCDF-7KQM",
              device_name: "Living room TV",
              client_id: "fiestaboard-tvos",
              app_version: "2.3",
              expires_in: 600,
              scope: "tv_panels",
            },
          });
        else if (path === "/api/auth/device/approve" || path === "/api/auth/device/deny") {
          expect(route.request().headers()["x-csrf-token"]).toBe("test_nonce");
          await route.fulfill({ json: { status: "ok" } });
        } else await route.fulfill({ status: 404, json: {} });
      });
      await page.goto(`/tests/layout/setup.html?mode=activate&theme=${theme}`);
      await expect(page.getByRole("button", { name: "Continue", exact: true })).toBeDisabled();
      await injectAxe(page);
      const axe = async () =>
        checkA11y(page, undefined, {
          axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } },
        });
      await axe();
      await page.screenshot({ path: `${shots}/impl-activate-entry-${width}-${theme}.png`, fullPage: true });
      await page.getByLabel("TV code", { exact: true }).fill("bcdf-7kqm");
      await page.getByRole("button", { name: "Continue", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Allow this TV?", exact: true })).toBeFocused();
      await expect(page.getByText("Living room TV", { exact: true })).toBeVisible();
      await axe();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `${shots}/impl-activate-consent-${width}-${theme}.png`, fullPage: true });
      await page.getByRole("button", { name: "Allow this TV", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Living room TV is signed in", exact: true })).toBeVisible();
      await axe();
      await page.screenshot({ path: `${shots}/impl-activate-approved-${width}-${theme}.png`, fullPage: true });
      await page.goto(`/tests/layout/setup.html?mode=reset&theme=${theme}`);
      await expect(page.getByRole("heading", { name: "Reset password", exact: true })).toBeVisible();
      await injectAxe(page);
      await axe();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `${shots}/impl-reset-password-${width}-${theme}.png`, fullPage: true });
    });
  }
}

for (const width of [390, 768, 1280]) {
  for (const theme of ["light", "dark"]) {
    for (const result of ["expired", "unavailable", "denied"] as const) {
      test(`TV ${result} recovery ${width} ${theme}`, async ({ page }) => {
        await page.setViewportSize({ width, height: 1000 });
        await page.route("**/api/auth/**", async (route) => {
          const path = new URL(route.request().url()).pathname;
          if (path === "/api/auth/status")
            await route.fulfill({
              json: {
                enabled: true,
                authenticated: true,
                username: "example",
                setup_required: false,
                tv_sign_in: { enabled: true },
              },
            });
          else if (path === "/api/auth/sessions/context")
            await route.fulfill({ json: { csrf_token: "test_nonce", expires_in: 600 } });
          else if (path === "/api/auth/device/inspect") {
            if (result === "denied")
              await route.fulfill({
                json: {
                  user_code: "BCDF-7KQM",
                  device_name: "Living room TV",
                  client_id: "fiestaboard-tvos",
                  expires_in: 600,
                  scope: "tv_panels",
                },
              });
            else
              await route.fulfill({
                status: 400,
                json: { error: result === "expired" ? "expired_token" : "invalid_grant" },
              });
          } else if (path === "/api/auth/device/deny") await route.fulfill({ json: { status: "ok" } });
          else await route.fulfill({ status: 404, json: {} });
        });
        await page.goto(`/tests/layout/setup.html?mode=activate&theme=${theme}&user_code=BCDF-7KQM`);
        if (result === "denied") await page.getByRole("button", { name: "Deny", exact: true }).click();
        const heading =
          result === "expired"
            ? "This code expired"
            : result === "unavailable"
              ? "This code is no longer available"
              : "Not allowed";
        await expect(page.getByRole("heading", { name: heading, exact: true })).toBeVisible();
        await injectAxe(page);
        await checkA11y(page, undefined, {
          axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } },
        });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: `${shots}/impl-activate-${result}-${width}-${theme}.png`, fullPage: true });
      });
    }
  }
}
