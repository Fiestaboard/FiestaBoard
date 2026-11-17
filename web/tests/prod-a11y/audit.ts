import { expect, type Page, type TestInfo } from "@playwright/test";
import type { AxeResults, RunOptions } from "axe-core";
import { injectAxe } from "axe-playwright";

import { campaign } from "./campaign";

export const axeOptions: RunOptions = {
  runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] },
  rules: { "color-contrast": { enabled: true }, "target-size": { enabled: true } },
};

export async function attachJson(testInfo: TestInfo, name: string, value: unknown) {
  await testInfo.attach(name, { body: Buffer.from(JSON.stringify(value, null, 2)), contentType: "application/json" });
}

export async function auditDocument(page: Page, testInfo: TestInfo, state: Record<string, unknown>) {
  const expectedDark = testInfo.project.use.colorScheme === "dark";
  await expect.poll(() => page.locator("html").evaluate((html) => html.classList.contains("dark"))).toBe(expectedDark);
  await expect(page.locator('[data-slot="skeleton"]:visible, [aria-busy="true"]:visible')).toHaveCount(0);
  await page.evaluate(async () => {
    await document.fonts.ready;
    // Let the normal route entrance finish without disabling motion. Infinite
    // animations are a separate manual/motion state, not an unbounded wait.
    await Promise.all(
      document.getAnimations().flatMap((animation) =>
        animation.effect?.getTiming().iterations !== Infinity ? [animation.finished.catch(() => undefined)] : [],
      ),
    );
    await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  });
  await injectAxe(page);
  const result: AxeResults = await page.evaluate((options) => {
    const axeWindow = window as unknown as { axe: typeof import("axe-core") };
    return axeWindow.axe.run(document, options);
  }, axeOptions);
  const rendered = await page.evaluate(() => ({
    url: location.href,
    title: document.title,
    htmlClass: document.documentElement.className,
    viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
    input: { coarse: matchMedia("(pointer: coarse)").matches, touchPoints: navigator.maxTouchPoints },
    prefersReducedMotion: matchMedia("(prefers-reduced-motion: reduce)").matches,
  }));
  // This artifact keeps complete violations AND incomplete/needs-review results.
  await attachJson(testInfo, "axe-full.json", {
    provenance: {
      campaign: campaign.kind,
      image: campaign.image,
      declaredSourceSha: campaign.sourceSha,
      runId: campaign.runId,
      dataset: campaign.dataset,
      auth: campaign.auth,
      project: testInfo.project.name,
      browser: page.context().browser()?.version(),
      state,
    },
    rendered,
    options: axeOptions,
    result,
    limits: "Automated rule outcome only. Incomplete rules and manual WCAG criteria require separate review.",
  });
  await testInfo.attach("settled-state.png", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
  if (result.incomplete.length > 0) {
    testInfo.annotations.push({
      type: "needs-manual-review",
      description: `${result.incomplete.length} incomplete axe rules; inspect axe-full.json`,
    });
  }
  expect(
    result.violations,
    `All-impact WCAG violations: ${result.violations.map((v) => `${v.id} (${v.impact})`).join(", ")}`,
  ).toEqual([]);
}
