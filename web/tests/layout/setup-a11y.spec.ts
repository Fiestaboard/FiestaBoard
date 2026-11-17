import { expect, test } from "@playwright/test";
import { injectAxe } from "axe-playwright";

import { checkSetupA11y } from "./setup-a11y";

test("only the kit logotype is exempt from contrast, with other content and logo rules still checked", async ({
  page,
}) => {
  await page.setContent(
    '<html lang="en"><head><title>Logotype exception guard</title></head><body><main><h1>Setup</h1><span class="logo-fiesta-text" style="color:#bbb">Fiesta</span><p id="ordinary">Ordinary form instructions</p></main></body></html>',
  );
  await injectAxe(page);
  await checkSetupA11y(page);
  await page.locator("#ordinary").evaluate((node) => {
    (node as HTMLElement).style.color = "#bbb";
  });
  await expect(checkSetupA11y(page)).rejects.toThrow(/accessibility violation/);
  await page.locator("#ordinary").evaluate((node) => {
    (node as HTMLElement).style.color = "#000";
  });
  await page.locator(".logo-fiesta-text").evaluate((node) => node.setAttribute("aria-checked", "true"));
  await expect(checkSetupA11y(page)).rejects.toThrow(/accessibility violation/);
});
