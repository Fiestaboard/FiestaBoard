#!/usr/bin/env node
/**
 * Captures a screenshot of the docs navbar for logo alignment evaluation.
 * Run from web/: node scripts/screenshot-navbar.mjs
 * Requires: docs site running on port 3001
 */

import { chromium } from '@playwright/test';
import { fileURLToPath } from 'url';
import path from 'path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const port = process.env.PORT || 3001;
const url = `http://localhost:${port}/`;

async function main() {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(url, { waitUntil: 'networkidle' });

  const navbar = await page.$('.navbar');
  const outPath = path.join(__dirname, '..', '..', 'docs-site', 'static', 'img', 'navbar-screenshot.png');
  await navbar.screenshot({ path: outPath });
  console.log('Screenshot saved to', outPath);

  await browser.close();
}

main().catch(console.error);
