import { expect, test } from "@playwright/test";
import { injectAxe } from "axe-playwright";

import { checkSetupA11y } from "./setup-a11y";

const stamp = "2026-11-05T17:39:00Z";
const sessions = [
  { id: "browser", kind: "browser", device_name: "Chrome on a computer", method: "password" },
  { id: "phone", kind: "mobile", device_name: "Example phone", client_id: "fiestaboard-ios", method: "pairing" },
  {
    id: "tv",
    kind: "tv",
    device_name: "Living room TV",
    client_id: "fiestaboard-tvos",
    method: "device_code",
    approved_by: { session_id: "phone", label: "Example phone", kind: "mobile", signed_in: true },
    last_shown_at: stamp,
    shown_panels: [{ panel_id: "Kitchen panel", last_shown_at: stamp }],
  },
  { id: "legacy", kind: "legacy", device_name: "Older TV app", method: "password" },
].map((row) => ({ ...row, created_at: stamp, last_active_at: stamp, expires_at: "2027-11-05T17:39:00Z" }));
const shots = process.env.WEB212_SHOTS ?? "test-results/web212-shots";
for (const width of [390, 768, 1280]) {
  for (const theme of ["light", "dark"]) {
    test(`sessions and QR pairing ${width} ${theme}`, async ({ page, baseURL }) => {
      await page.setViewportSize({ width, height: 1000 });
      await page.emulateMedia({ reducedMotion: "reduce" });
      // Serve the same fixture under a network origin so the normal live
      // state is distinct from the separately covered localhost warning.
      await page.route("http://fiestapi.test/**", async (route) => {
        const url = new URL(route.request().url());
        await route.fulfill({ response: await route.fetch({ url: `${baseURL}${url.pathname}${url.search}` }) });
      });
      let state = "pending";
      const revoked: string[] = [];
      let cancellations = 0;
      const createBodies: unknown[] = [];
      await page.route("**/api/panels", (route) =>
        route.fulfill({ json: { panels: [{ id: "Kitchen panel", name: "Kitchen board panel" }], total: 1 } }),
      );
      await page.route("**/api/auth/**", async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path === "/api/auth/sessions/context")
          await route.fulfill({ json: { csrf_token: "test_nonce", expires_in: 600 } });
        else if (path === "/api/auth/device/settings") await route.fulfill({ json: { enabled: true } });
        else if (path === "/api/auth/sessions")
          await route.fulfill({
            json: { sessions: sessions.filter((row) => !revoked.includes(row.id)), current_session_id: "browser" },
          });
        else if (path === "/api/auth/pairing" && route.request().method() === "POST") {
          expect(route.request().headers()["x-csrf-token"]).toBe("test_nonce");
          createBodies.push(route.request().postDataJSON());
          await route.fulfill({
            json: {
              pairing_id: "offer",
              qr_payload: "fiestaboard://pair#v=1&hub=http%3A%2F%2Ffiestapi.local&code=test_only",
              hub: "http://fiestapi.local",
              hub_addresses: [{ url: "http://fiestapi.local", kind: "mdns" }],
              expires_in: 300,
            },
          });
        } else if (path === "/api/auth/pairing" && route.request().method() === "DELETE") {
          cancellations++;
          await route.fulfill({ json: { status: "ok" } });
        } else if (path === "/api/auth/pairing/offer")
          await route.fulfill({ json: { state, device_name: "Example phone", session_id: "new-phone" } });
        else if (path.startsWith("/api/auth/sessions/") && route.request().method() === "DELETE") {
          revoked.push(path.split("/").at(-1)!);
          await route.fulfill({ json: { status: "ok", also_signed_out: [] } });
        } else await route.fulfill({ status: 404, json: {} });
      });
      await page.goto(`http://fiestapi.test/tests/layout/setup.html?theme=${theme}`);
      await expect(page.getByRole("heading", { name: "Phones", exact: true })).toBeVisible();
      await injectAxe(page);
      await checkSetupA11y(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (shots) await page.screenshot({ path: `${shots}/impl-sessions-${width}-${theme}.png`, fullPage: false });
      await page.getByRole("button", { name: "Connect a phone", exact: true }).click();
      await expect(page.getByRole("img", { name: "Scan with the FiestaBoard app" })).toBeVisible();
      if (width === 390) {
        const bounds = await page.getByRole("dialog").boundingBox();
        expect(Math.round(bounds!.x)).toBe(0);
        expect(Math.round(bounds!.width)).toBe(390);
        expect(
          (await page.getByRole("button", { name: "Make a new code", exact: true }).boundingBox())!.height,
        ).toBeGreaterThanOrEqual(44);
      }
      await checkSetupA11y(page);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      if (shots) await page.screenshot({ path: `${shots}/impl-qr-live-${width}-${theme}.png`, fullPage: false });
      expect(createBodies).toEqual([{}]);
      state = "claimed";
      await expect(page.getByText("Example phone is connected", { exact: true })).toBeVisible();
      await expect(page.getByRole("img", { name: "Scan with the FiestaBoard app" })).toHaveCount(0);
      if (width === 390)
        expect(
          (await page.getByRole("button", { name: "Sign it out", exact: true }).boundingBox())!.height,
        ).toBeGreaterThanOrEqual(44);
      await checkSetupA11y(page);
      if (shots) await page.screenshot({ path: `${shots}/impl-qr-connected-${width}-${theme}.png`, fullPage: false });
      await page.getByRole("button", { name: "Sign it out", exact: true }).click();
      await expect(page.getByRole("dialog")).toHaveCount(0);
      expect(revoked).toEqual(["new-phone"]);
      await expect.poll(() => cancellations).toBe(1);
      await page.getByRole("button", { name: "Revoke Example phone", exact: true }).click();
      await expect(page.getByRole("checkbox")).toBeChecked();
      await checkSetupA11y(page);
      if (shots) await page.screenshot({ path: `${shots}/impl-revoke-${width}-${theme}.png`, fullPage: false });
      await page.getByRole("checkbox").uncheck();
      await page.getByRole("button", { name: "Sign out phone", exact: true }).click();
      await expect(page.getByRole("listitem", { name: "Example phone", exact: true })).toHaveCount(0);
      await expect(page.getByRole("listitem", { name: "Living room TV", exact: true })).toBeVisible();
    });
  }
}
