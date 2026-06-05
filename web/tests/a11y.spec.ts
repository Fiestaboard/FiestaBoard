/**
 * Accessibility regression tests.
 *
 * Runs axe-core against the main pages and fails on critical+serious
 * WCAG violations. Moderate/minor findings are reported but don't fail
 * CI so the test stays useful as a regression guard without blocking on
 * known cosmetic issues. To debug, set DEBUG_A11Y=1 to log every finding.
 *
 * Pages covered:
 *   - /          Dashboard (with and without pages configured)
 *   - /pages     Pages list
 *   - /schedule  Schedule
 *   - /integrations Integrations marketplace
 *   - /settings  Settings (default tab)
 *   - /login     Login (auth disabled in this env, so navigated directly)
 */
import type { Page } from "@playwright/test";
import { getViolations, injectAxe } from "axe-playwright";

import {
  configureBoard,
  createPage,
  deleteAllPages,
  deleteAllSchedules,
  expect,
  resetToSingleBoard,
  suppressWizard,
  test,
} from "./helpers";

const FAIL_IMPACTS = new Set(["critical", "serious"]);

// `color-contrast` is excluded for now — it depends on the design system's
// muted/secondary tokens and warrants a focused palette sweep rather than
// being chased per-component. Tracked separately; the rest of the audit
// still guards against regressions in semantic / labelling rules.
const RULES_TO_SKIP = ["color-contrast"];

async function auditPage(page: Page, path: string, waitForSelector?: string) {
  await page.goto(path);
  if (waitForSelector) {
    await page.waitForSelector(waitForSelector, { timeout: 15_000 });
  } else {
    // Give the layout a beat to settle (web fonts, hydration, etc.).
    await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => {});
  }

  await injectAxe(page);
  const axeOptions = {
    // Restrict to widely-accepted WCAG rulesets so we don't flake on
    // experimental checks. WCAG 2.1 AA is the de-facto compliance bar.
    runOnly: {
      type: "tag" as const,
      values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"],
    },
    rules: Object.fromEntries(RULES_TO_SKIP.map((id) => [id, { enabled: false }])),
  };
  const violations = await getViolations(page, undefined, axeOptions);

  const summarised = violations.map((v) => ({
    id: v.id,
    impact: v.impact,
    help: v.help,
    helpUrl: v.helpUrl,
    nodes: v.nodes.length,
    sample: v.nodes.slice(0, 3).map((n) => n.target),
  }));

  if (process.env.DEBUG_A11Y || summarised.length > 0) {
    // eslint-disable-next-line no-console
    console.log(`[a11y] ${path}:`, JSON.stringify(summarised, null, 2));
  }

  const failing = violations.filter((v) => FAIL_IMPACTS.has(v.impact || ""));
  return { violations, failing };
}

test.describe("Accessibility (axe)", () => {
  test.beforeEach(async ({ page }) => {
    await configureBoard();
    await resetToSingleBoard();
    await suppressWizard(page);
    await deleteAllSchedules();
    await deleteAllPages();
  });

  test("dashboard (empty) has no critical or serious a11y violations", async ({ page }) => {
    const { failing } = await auditPage(page, "/", "h1");
    expect(failing, `Dashboard a11y violations:\n${JSON.stringify(failing, null, 2)}`).toEqual([]);
  });

  test("dashboard (with active page) has no critical or serious a11y violations", async ({ page }) => {
    await createPage("A11y Test Page");
    const { failing } = await auditPage(page, "/", "h1");
    expect(failing).toEqual([]);
  });

  test("pages list has no critical or serious a11y violations", async ({ page }) => {
    await createPage("A11y List Page");
    const { failing } = await auditPage(page, "/pages", "h1");
    expect(failing).toEqual([]);
  });

  test("schedule page has no critical or serious a11y violations", async ({ page }) => {
    const { failing } = await auditPage(page, "/schedule", "h1");
    expect(failing).toEqual([]);
  });

  test("integrations page has no critical or serious a11y violations", async ({ page }) => {
    const { failing } = await auditPage(page, "/integrations", "h1");
    expect(failing).toEqual([]);
  });

  test("settings page has no critical or serious a11y violations", async ({ page }) => {
    const { failing } = await auditPage(page, "/settings", "h1");
    expect(failing).toEqual([]);
  });

  test("login page has no critical or serious a11y violations", async ({ page }) => {
    // The login page is normally only reachable when auth is enabled, but
    // navigating directly still renders its loading shell, which exercises
    // the viewport meta + layout chrome we care about. If auth is disabled
    // the page redirects home — skip the assertion in that case.
    await page.goto("/login");
    const url = page.url();
    test.skip(!url.includes("/login"), "login redirected (auth disabled in this env)");
    await injectAxe(page);
    const violations = await getViolations(page, undefined, {
      runOnly: {
        type: "tag" as const,
        values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"],
      },
      rules: Object.fromEntries(RULES_TO_SKIP.map((id) => [id, { enabled: false }])),
    });
    const failing = violations.filter((v) => FAIL_IMPACTS.has(v.impact || ""));
    expect(failing).toEqual([]);
  });
});
