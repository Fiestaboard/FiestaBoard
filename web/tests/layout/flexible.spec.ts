import { expect, test } from "@playwright/test";
import { checkA11y, injectAxe } from "axe-playwright";

for (const width of [375, 1280]) {
  test(`flexible editor saves keyboard changes without horizontal overflow at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/tests/layout/flexible.html");
    await page.getByLabel("Block 1 text").fill("Good morning");
    await page.getByRole("button", { name: "Add spacer" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("button", { name: "Remove block 2" })).toBeVisible();
    await page.getByText("Display restrictions", { exact: true }).focus();
    await page.keyboard.press("Enter");
    await page.getByRole("checkbox", { name: "LED displays" }).focus();
    await page.keyboard.press("Space");
    await expect(page.getByRole("checkbox", { name: "LED displays" })).toBeChecked();
    await page.getByRole("button", { name: "Save page" }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("status", { name: "Saved document" })).toContainText(
      '"expected_revision":"fixture-one"',
    );
    const saved = JSON.parse((await page.getByRole("status", { name: "Saved document" }).textContent())!);
    expect(saved.blocks[0]).toMatchObject({ id: "heading", text: "Good morning", future: true });
    expect(saved.blocks[1].kind).toBe("spacer");
    expect(saved.targets).toEqual({ technology: ["led_matrix"] });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await injectAxe(page);
    await checkA11y(page, "main", { detailedReport: true });
  });
}

for (const [width, height] of [
  [32, 8],
  [52, 16],
  [64, 64],
]) {
  test(`physical preview uses all ${width} by ${height} pixels`, async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 844 });
    await page.goto(`/tests/layout/flexible.html?physical=1&width=${width}&height=${height}`);
    const matrix = page.locator('[data-slot="led-matrix-display"]');
    await expect(matrix).toHaveAttribute("data-matrix-width", String(width));
    await expect(matrix).toHaveAttribute("data-matrix-height", String(height));
    await expect(matrix.locator("canvas")).toBeVisible();
    expect(
      await matrix.locator("canvas").evaluate((canvas: HTMLCanvasElement) => {
        const ctx = canvas.getContext("2d")!;
        const pixels = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
        return pixels.some(
          (red, index) => index % 4 === 0 && red > 200 && pixels[index + 1] < 30 && pixels[index + 2] < 30,
        );
      }),
    ).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375);
    await injectAxe(page);
    await expect(page.locator("main")).toHaveCSS("opacity", "1");
    await checkA11y(page, "main", { detailedReport: true });
  });
}
