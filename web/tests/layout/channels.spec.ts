import { expect, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

for (const width of [390, 768, 1280]) {
  for (const theme of ["light", "dark"]) {
    test(`channel chooser and confirmation ${width} ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      const posted: unknown[] = [];
      await page.route("**/api/system/channel/versions", async (route) => {
        await route.fulfill({
          json: { channel_versions: { stable: "10.3.3", beta: "10.3.4-beta.0", alpha: "11.0.0-alpha.1" } },
        });
      });
      await page.route("**/api/system/channel", async (route) => {
        if (route.request().method() === "POST") {
          posted.push(route.request().postDataJSON());
          await route.fulfill({ json: { status: "queued", channel: "alpha", tag: "v11-alpha" } });
        } else {
          await route.fulfill({
            json: {
              channel: "stable",
              running_channel: "stable",
              running_version: "10.3.3",
              available_channels: ["stable", "beta", "alpha"],
              channel_versions: { stable: "10.3.3", beta: "10.3.4-beta.0", alpha: "11.0.0-alpha.1" },
              can_switch: true,
              reason: null,
            },
          });
        }
      });
      await page.goto(`/tests/layout/channels.html?theme=${theme}`);
      await expect(page.getByRole("radio", { name: /Stable/ })).toBeChecked();
      await expect(page.getByText("11.0.0-alpha.1")).toBeVisible();
      await injectAxe(page);
      await checkA11y(page, undefined, {
        axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } },
      });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `/tmp/cx-channel-shots/chooser-${width}-${theme}.png`, fullPage: true });
      // Arrow keys explore without opening a dialog; Enter explicitly activates the candidate.
      await page.getByRole("radio", { name: /Stable/ }).focus();
      await page.keyboard.press("ArrowDown");
      await expect(page.getByRole("radio", { name: /Beta/ })).toBeChecked();
      await expect(page.getByRole("radio", { name: /Beta/ })).toBeFocused();
      await expect(page.getByRole("alertdialog")).toHaveCount(0);
      expect(posted).toHaveLength(0);
      await page.keyboard.press("Enter");
      await expect(page.getByRole("alertdialog")).toBeVisible();
      await page.getByRole("button", { name: "Cancel" }).click();
      await expect(page.getByRole("radio", { name: /Beta/ })).toBeChecked();
      await page.getByRole("radio", { name: /Alpha preview/ }).click();
      await page.getByRole("button", { name: "Switch channel" }).click();
      await expect(page.getByRole("alertdialog")).toContainText("automatic backup");
      expect(posted).toHaveLength(0);
      await checkA11y(page, undefined, {
        axeOptions: { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21aa"] } },
      });
      await page.screenshot({ path: `/tmp/cx-channel-shots/confirm-${width}-${theme}.png`, fullPage: true });
      await page.getByRole("button", { name: "Switch channel" }).click();
      await expect.poll(() => posted).toEqual([{ channel: "alpha", confirm_major_upgrade: true }]);
    });
  }
}
