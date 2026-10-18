import { expect, test } from "@playwright/test";

for (const width of [375, 390, 1280]) {
  test(`the whole LED canvas fits the editor preview at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/tests/layout/");
    const canvas = page.locator("canvas");
    await expect(canvas).toBeVisible();
    await testInfo.attach("layout", {
      body: JSON.stringify({
        canvas: await canvas.boundingBox(),
        container: await page.getByTestId("editor-preview").boundingBox(),
      }),
      contentType: "application/json",
    });
    await expect(async () => {
      const board = await canvas.boundingBox();
      const container = await page.getByTestId("editor-preview").boundingBox();
      expect(board!.width).toBeGreaterThan(0);
      expect(board!.x).toBeGreaterThanOrEqual(container!.x - 1);
      expect(board!.x + board!.width).toBeLessThanOrEqual(container!.x + container!.width + 1);
    }).toPass({ timeout: 3000 });
  });
}

test("drawing still hit-tests the rightmost scaled flap tile on a phone", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 844 });
  await page.goto("/tests/layout/");
  await page.getByRole("button", { name: "Toggle drawing" }).click();
  const tile = page.locator('[data-draw-surface="true"] [data-row="0"][data-col="21"]');
  await tile.click();
  await expect(page.locator("output")).toHaveText('[{"row":0,"col":21}]');
});
