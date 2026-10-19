import { expect, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

for (const theme of ["light", "dark"]) {
  for (const width of [320, 375, 1280]) {
    test(`FiestaBot reply and activity fit ${width}px in ${theme}`, async ({ page }, testInfo) => {
      await page.setViewportSize({ width, height: 850 });
      await page.goto(`/tests/layout/chat.html?theme=${theme}`);
      await page.getByRole("button", { name: "Open assistant", exact: true }).click();
      const dialog = page.getByRole("dialog", { name: "FiestaBot AI chat" });
      await page.getByRole("textbox", { name: "Message", exact: true }).fill("Create a golden hour page");
      await page.getByRole("button", { name: "Send", exact: true }).click();
      await expect(dialog.getByText(/Your Golden hour page is ready/)).toBeVisible();
      await expect(dialog.getByTestId("ai-turn-activity")).toHaveCount(1);
      const bounds = await dialog.boundingBox();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
      expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
      for (const label of ["History", "New chat", "Minimize FiestaBot", "Close FiestaBot"]) {
        const button = dialog.getByRole("button", { name: label, exact: true });
        const box = await button.boundingBox();
        expect(box!.x).toBeGreaterThanOrEqual(bounds!.x);
        expect(box!.x + box!.width).toBeLessThanOrEqual(bounds!.x + bounds!.width);
      }
      await injectAxe(page);
      await checkA11y(page, "#fiestabot-chat-drawer");
      await page.screenshot({ path: testInfo.outputPath(`fiestabot-${theme}-${width}.png`) });
      const activity = dialog.getByTestId("ai-turn-activity");
      await activity.getByRole("button", { name: /Finished/ }).click();
      await expect(activity.getByTestId("ai-activity-details")).toBeVisible();
      await page.screenshot({ path: testInfo.outputPath(`fiestabot-activity-${theme}-${width}.png`) });
      await activity.getByRole("button", { name: /Finished/ }).click();
      await page.getByRole("button", { name: "Minimize FiestaBot", exact: true }).click();
      const restore = page.getByRole("button", { name: /Open FiestaBot.*Finished/ });
      await expect(restore).toBeVisible();
      await expect(restore).toBeFocused();
      await expect(dialog).toBeHidden();
      await page.getByRole("textbox", { name: "Page name", exact: true }).fill("Keep editing while minimized");
      await restore.click();
      await expect(page.getByRole("textbox", { name: "Message", exact: true })).toBeFocused();
      await expect(dialog.getByText(/Your Golden hour page is ready/)).toBeVisible();
      await page.getByRole("button", { name: "Close FiestaBot", exact: true }).click();
      await expect(page.getByRole("button", { name: "Open assistant", exact: true })).toBeFocused();
    });
  }
}

test("minimized work can be stopped with reduced motion enabled", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 850 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/tests/layout/chat.html?scenario=thinking&theme=dark");
  await page.getByRole("button", { name: "Open assistant", exact: true }).click();
  await page.getByRole("textbox", { name: "Message", exact: true }).fill("Think about a sunset");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  await page.getByRole("button", { name: "Minimize FiestaBot", exact: true }).click();
  await expect(page.getByRole("button", { name: /Open FiestaBot.*Thinking/ })).toBeVisible();
  const dock = page.locator(".fiestabot-dock");
  await injectAxe(page);
  await checkA11y(page, ".fiestabot-dock");
  expect(
    await dock.locator(".fiestabot-mark").evaluate((element) => getComputedStyle(element, "::before").animationName),
  ).toBe("none");
  await page.screenshot({ path: testInfo.outputPath("fiestabot-minimized-working.png") });
  await page.getByRole("button", { name: "Stop", exact: true }).click();
  await expect(page.getByRole("button", { name: /Open FiestaBot.*Stopped/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Open FiestaBot.*Stopped/ })).toBeFocused();
});

test("an approval remains visible when activity is collapsed and after restoring", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 850 });
  await page.goto("/tests/layout/chat.html?scenario=approval");
  await page.getByRole("button", { name: "Open assistant", exact: true }).click();
  await page.getByRole("textbox", { name: "Message", exact: true }).fill("Delete the sunset page");
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const approval = page.getByRole("dialog", { name: "FiestaBot AI chat" }).getByRole("button", { name: /^Approve$/ });
  await expect(approval).toBeVisible();
  await page.getByRole("button", { name: "Minimize FiestaBot", exact: true }).click();
  await page.getByRole("button", { name: /Open FiestaBot.*Approval needed/ }).click();
  await expect(approval).toBeVisible();
});

test("long translated activity labels fit a narrow phone", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 320, height: 850 });
  await page.context().addCookies([{ name: "NEXT_LOCALE", value: "ru", url: "http://127.0.0.1:4398" }]);
  await page.goto("/tests/layout/chat.html");
  await page.getByRole("button", { name: "Open assistant", exact: true }).click();
  await page.locator("#ai-chat-input").fill("Make a golden hour page");
  await page.locator("#ai-chat-input").press("Enter");
  const activity = page.getByTestId("ai-turn-activity");
  await expect(activity).toContainText("Выполнено действий: 2");
  expect(await activity.evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(true);
  const label = activity.getByText("Завершено", { exact: true });
  await expect(label).toBeVisible();
  expect(await label.evaluate((e) => e.clientWidth >= e.scrollWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("fiestabot-russian-320.png") });
});
