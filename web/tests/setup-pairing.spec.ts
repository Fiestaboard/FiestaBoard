import { expect, test } from "@playwright/test";

const origin = "http://127.0.0.1:4430";
const credentials = { username: "admin", password: "correct-password" };

for (const prefix of ["", "/test-prefix"]) {
  test(`phone QR claim and selective phone/TV sign-out ${prefix || "root"}`, async ({ page, playwright }) => {
    const api = `${origin}${prefix}/api`;
    const mobile = await playwright.request.newContext();
    const tv = await playwright.request.newContext();
    try {
      const status = await (await page.request.get(`${api}/auth/status`)).json();
      expect(
        (
          await page.request.post(`${api}/auth/${status.setup_required ? "setup" : "login"}`, { data: credentials })
        ).ok(),
      ).toBe(true);
      const mutate = async (path: string, method: string, data?: unknown) => {
        const { csrf_token } = await (await page.request.get(`${api}/auth/sessions/context`)).json();
        return page.request.fetch(`${api}${path}`, {
          method,
          data,
          headers: { Origin: origin, "X-CSRF-Token": csrf_token },
        });
      };
      expect((await mutate("/auth/device/settings", "PUT", { enabled: true })).ok()).toBe(true);
      // Keep setup out of this signed-in settings flow without writing a real display.
      await page.addInitScript(() => localStorage.setItem("fiestaboard_wizard_complete", "true"));
      expect(
        (
          await page.request.put(`${api}/config/board`, {
            data: { api_mode: "local", host: "127.0.0.1", local_api_key: "acceptance-stub" },
          })
        ).ok(),
      ).toBe(true);
      await page.goto(`${prefix}/settings/account`);
      await expect(page.getByText("Signed-in devices", { exact: true })).toBeVisible();
      const response = page.waitForResponse(
        (res) => res.url().endsWith("/auth/pairing") && res.request().method() === "POST",
      );
      await page.getByRole("button", { name: "Connect a phone", exact: true }).click();
      const pairing = await response;
      expect(pairing.ok()).toBe(true);
      const offer = await pairing.json();
      const hub = new URL(offer.hub);
      expect(["localhost", "127.0.0.1", "[::1]"]).not.toContain(hub.hostname);
      await expect(page.getByRole("img", { name: "Scan with the FiestaBoard app" })).toBeVisible();
      const code = new URLSearchParams(new URL(offer.qr_payload).hash.slice(1)).get("code");
      const claimed = await mobile.post(`${api}/auth/pairing/claim`, {
        data: {
          pairing_code: code,
          client_id: "fiestaboard-ios",
          device_name: "Acceptance phone",
          app_version: "test",
        },
      });
      expect(claimed.ok()).toBe(true);
      const phone = await claimed.json();
      await expect(page.getByText("Acceptance phone is connected", { exact: true })).toBeVisible();
      await expect(page.getByRole("img", { name: "Scan with the FiestaBoard app" })).toHaveCount(0);
      await page.getByRole("button", { name: "Done", exact: true }).click();
      const phoneHeaders = { Authorization: `Bearer ${phone.access_token}` };
      const authorize = await tv.post(`${api}/auth/device/authorize`, {
        data: { client_id: "fiestaboard-tvos", device_name: "Phone-approved TV", app_version: "test" },
      });
      expect(authorize.status()).toBe(200);
      const challenge = await authorize.json();
      expect(
        (
          await mobile.post(`${api}/auth/device/approve`, {
            data: { user_code: challenge.user_code },
            headers: phoneHeaders,
          })
        ).ok(),
      ).toBe(true);
      const token = await tv.post(`${api}/auth/device/token`, {
        data: { client_id: "fiestaboard-tvos", device_code: challenge.device_code },
      });
      expect(token.ok()).toBe(true);
      const tvToken = await token.json();
      const tvHeaders = { Authorization: `Bearer ${tvToken.access_token}` };
      await page.reload();
      await page.getByRole("button", { name: "Revoke Acceptance phone", exact: true }).click();
      const confirmation = page.getByRole("alertdialog");
      await expect(confirmation.getByRole("checkbox")).toBeChecked();
      await expect(confirmation).toContainText("Phone-approved TV");
      await confirmation.getByRole("checkbox").uncheck();
      await confirmation.getByRole("button", { name: "Sign out phone", exact: true }).click();
      await expect(page.getByRole("listitem", { name: "Acceptance phone", exact: true })).toHaveCount(0);
      expect((await mobile.get(`${api}/auth/device/tvs`, { headers: phoneHeaders })).status()).toBe(401);
      expect((await tv.get(`${api}/panels`, { headers: tvHeaders })).ok()).toBe(true);
      expect((await page.request.get(`${api}/auth/sessions`)).ok()).toBe(true);
      await page.getByRole("button", { name: "Revoke Phone-approved TV", exact: true }).click();
      await expect(page.getByRole("listitem", { name: "Phone-approved TV", exact: true })).toHaveCount(0);
      expect((await tv.get(`${api}/panels`, { headers: tvHeaders })).status()).toBe(401);
    } finally {
      await mobile.dispose();
      await tv.dispose();
    }
  });
}
