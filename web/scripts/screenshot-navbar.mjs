#!/usr/bin/env node
/**
 * Captures a screenshot of the docs navbar for logo alignment evaluation.
 * Run from web/: node scripts/screenshot-navbar.mjs
 * Requires: docs site running on port 3001
 */

import { chromium } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const port = process.env.PORT || 3001;
const url = `http://localhost:${port}/`;

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(url, { waitUntil: "networkidle" });

  const navbar = await page.$(".navbar");
  // Docs site lives in Fiestaboard/fiestaboard.github.io now; point
  // DOCS_SITE_DIR at a local checkout to write into it, otherwise the
  // screenshot lands in web/screenshots-output/ (gitignored).
  const siteRoot = process.env.DOCS_SITE_DIR
    ? path.resolve(process.env.DOCS_SITE_DIR)
    : path.join(__dirname, "..", "screenshots-output");
  const outPath = path.join(siteRoot, "static", "img", "navbar-screenshot.png");
  // (Playwright creates missing parent directories for screenshot paths.)
  await navbar.screenshot({ path: outPath });
  console.log("Screenshot saved to", outPath);

  await browser.close();
}

main().catch(console.error);
