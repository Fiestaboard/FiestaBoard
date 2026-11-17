import { expect, test } from "@playwright/test";

// Use the default browser channel too: signing out must remain responsive
// without notification permission or the full Chromium notification service.
test("sign-out with an active worker preserves a responsive signed-out page", async ({ page }) => {
  await page.goto("/tests/layout/push-cleanup.html");
  await page.evaluate(async () => {
    await navigator.serviceWorker.register("/sw.js");
    await navigator.serviceWorker.ready;
  });
  await page.evaluate(async () => {
    const source = "/src/lib/pwa/sign-out.ts";
    const { clearAccountDataOnDevice } = await import(/* @vite-ignore */ source);
    await clearAccountDataOnDevice();
  });
  await page.reload();
  await expect(page).toHaveTitle("Signed out");
});
