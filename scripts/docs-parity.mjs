#!/usr/bin/env node
/**
 * docs-parity.mjs — freeze and verify the URL surface of the docs site.
 *
 * The docs-site extraction (see the docs-site extraction plan) must not
 * change a single URL on fiestaboard.app. This tool makes that checkable:
 * it reduces a Docusaurus build directory to a manifest of routes, redirect
 * stubs, sitemap entries, and static assets, then diffs manifests or runs a
 * hand-picked fixture of URLs against either a build directory or a live
 * host.
 *
 * Usage:
 *   node scripts/docs-parity.mjs <buildDir>                        # manifest → stdout
 *   node scripts/docs-parity.mjs <buildDir> --compare <baseline>   # diff; exit 1 on
 *                                                                  # added/removed routes,
 *                                                                  # removed redirects, or
 *                                                                  # changed redirect targets
 *   node scripts/docs-parity.mjs <buildDir> --fixture <fixture>    # fixture vs build dir
 *   node scripts/docs-parity.mjs --host <origin> --fixture <fixture>  # fixture vs live host
 *
 * --pr-mode skips fixture entries marked "fullBuildOnly": true — those cover
 * historical version snapshots that DOCS_PR_MODE=1 builds don't compile.
 *
 * Content changes are reported but never fail the diff — only the URL
 * surface is frozen.
 */

import { readFileSync, readdirSync, statSync, existsSync } from "node:fs";
import { join, relative, basename, dirname } from "node:path";

// ---------------------------------------------------------------- helpers

function fail(msg) {
  console.error(`docs-parity: ${msg}`);
  process.exit(2);
}

function walk(dir, files = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) walk(full, files);
    else files.push(full);
  }
  return files;
}

// A client-redirect stub is a tiny page whose only job is a meta refresh.
const META_REFRESH_RE =
  /<meta\s+http-equiv="refresh"\s+content="0;\s*url=([^"]+)"/i;

function redirectTarget(html) {
  const m = html.match(META_REFRESH_RE);
  return m ? m[1] : null;
}

// Strip content hashes from a file name so the inventory is stable across
// rebuilds: `styles.abc123de.css` → `styles.css`, `logo-3f2a1b4c.png` → `logo.png`.
function stem(name) {
  return name
    .replace(/[.-][a-f0-9]{8,}(?=\.[a-z0-9]+$)/i, "")
    .replace(/[.-][a-f0-9]{8,}(?=\.[a-z0-9]+\.map$)/i, "");
}

function sortedUnique(arr) {
  return [...new Set(arr)].sort();
}

// ---------------------------------------------------------------- manifest

const PRESENCE_FILES = [
  ".nojekyll",
  "CNAME",
  "robots.txt",
  "llms.txt",
  "llms-full.txt",
  "search-index.json",
  "plugin-stats.json",
  "sitemap.xml",
  "404.html",
];

function buildManifest(buildDir) {
  if (!existsSync(buildDir)) fail(`build dir not found: ${buildDir}`);
  const files = walk(buildDir);

  const routes = [];
  const redirects = {};
  for (const file of files) {
    if (basename(file) !== "index.html") continue;
    const rel = relative(buildDir, dirname(file));
    const route = rel === "" ? "/" : `/${rel.split("\\").join("/")}`;
    const target = redirectTarget(readFileSync(file, "utf8"));
    if (target) redirects[route] = target;
    else routes.push(route);
  }

  let sitemap = [];
  const sitemapPath = join(buildDir, "sitemap.xml");
  if (existsSync(sitemapPath)) {
    const xml = readFileSync(sitemapPath, "utf8");
    sitemap = sortedUnique(
      [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) =>
        new URL(m[1]).pathname.replace(/\/$/, "") || "/",
      ),
    );
  }

  const assets = sortedUnique(
    files
      .filter((f) => basename(f) !== "index.html")
      .map((f) => {
        const rel = relative(buildDir, f);
        return join(dirname(rel), stem(basename(rel))).split("\\").join("/");
      }),
  );

  const presence = {};
  for (const name of PRESENCE_FILES) {
    const p = join(buildDir, name);
    presence[name] = existsSync(p)
      ? name === "CNAME"
        ? readFileSync(p, "utf8").trim()
        : true
      : false;
  }

  return {
    routes: routes.sort(),
    redirects: Object.fromEntries(
      Object.entries(redirects).sort(([a], [b]) => a.localeCompare(b)),
    ),
    sitemap,
    assets,
    presence,
  };
}

// ---------------------------------------------------------------- compare

function diffSets(a, b) {
  const A = new Set(a);
  const B = new Set(b);
  return {
    added: b.filter((x) => !A.has(x)),
    removed: a.filter((x) => !B.has(x)),
  };
}

function compare(manifest, baselinePath) {
  const baseline = JSON.parse(readFileSync(baselinePath, "utf8"));
  let failed = false;

  const routes = diffSets(baseline.routes, manifest.routes);
  if (routes.added.length || routes.removed.length) {
    failed = true;
    for (const r of routes.removed) console.error(`ROUTE REMOVED   ${r}`);
    for (const r of routes.added) console.error(`ROUTE ADDED     ${r}`);
  }

  for (const [path, target] of Object.entries(baseline.redirects)) {
    const now = manifest.redirects[path];
    if (now === undefined) {
      // A redirect that became a real page still serves the URL — report only.
      if (manifest.routes.includes(path)) {
        console.log(`redirect became page (ok): ${path}`);
      } else {
        failed = true;
        console.error(`REDIRECT REMOVED ${path} (was → ${target})`);
      }
    } else if (now !== target) {
      failed = true;
      console.error(`REDIRECT TARGET  ${path}: ${target} → ${now}`);
    }
  }
  for (const path of Object.keys(manifest.redirects)) {
    if (!(path in baseline.redirects) && !baseline.routes.includes(path))
      console.log(`redirect added (ok): ${path} → ${manifest.redirects[path]}`);
  }

  const sitemap = diffSets(baseline.sitemap, manifest.sitemap);
  for (const s of sitemap.removed) console.log(`sitemap removed: ${s}`);
  for (const s of sitemap.added) console.log(`sitemap added:   ${s}`);

  const assets = diffSets(baseline.assets, manifest.assets);
  if (assets.added.length || assets.removed.length)
    console.log(
      `assets: +${assets.added.length} -${assets.removed.length} (report only)`,
    );
  for (const a of assets.removed) console.log(`  asset removed: ${a}`);

  for (const [name, value] of Object.entries(baseline.presence)) {
    const now = manifest.presence[name];
    if (JSON.stringify(now) !== JSON.stringify(value)) {
      failed = true;
      console.error(`PRESENCE        ${name}: ${JSON.stringify(value)} → ${JSON.stringify(now)}`);
    }
  }

  if (failed) {
    console.error("docs-parity: URL surface changed — see above.");
    process.exit(1);
  }
  console.log("docs-parity: URL surface unchanged.");
}

// ---------------------------------------------------------------- fixture

async function runFixtureStatic(fixture, buildDir) {
  const failures = [];
  for (const entry of fixture) {
    const rel = entry.path.replace(/^\//, "");
    const asFile = join(buildDir, rel);
    const asPage = join(buildDir, rel, "index.html");
    if (entry.expect === "file") {
      if (!existsSync(asFile)) {
        failures.push(`${entry.path}: file missing`);
        continue;
      }
      if (
        entry.contains &&
        !readFileSync(asFile, "utf8").includes(entry.contains)
      )
        failures.push(`${entry.path}: does not contain ${JSON.stringify(entry.contains)}`);
      continue;
    }
    if (!existsSync(asPage)) {
      failures.push(`${entry.path}: no index.html`);
      continue;
    }
    const target = redirectTarget(readFileSync(asPage, "utf8"));
    if (entry.expect === "redirect") {
      if (!target) failures.push(`${entry.path}: expected redirect, got page`);
      else if (entry.target && target !== entry.target)
        failures.push(`${entry.path}: redirects to ${target}, expected ${entry.target}`);
    } else if (entry.expect === "page") {
      if (target) failures.push(`${entry.path}: expected page, got redirect → ${target}`);
    }
  }
  return failures;
}

async function runFixtureLive(fixture, host) {
  const failures = [];
  for (const entry of fixture) {
    const url = host.replace(/\/$/, "") + entry.path;
    let res;
    try {
      res = await fetch(url, { redirect: "follow" });
    } catch (e) {
      failures.push(`${entry.path}: fetch failed (${e.message})`);
      continue;
    }
    if (!res.ok) {
      failures.push(`${entry.path}: HTTP ${res.status}`);
      continue;
    }
    const body = await res.text();
    const target = redirectTarget(body);
    if (entry.expect === "redirect") {
      // GitHub Pages serves redirect stubs as 200 HTML with a meta refresh.
      if (!target) failures.push(`${entry.path}: expected redirect stub, got page`);
      else if (entry.target && target !== entry.target)
        failures.push(`${entry.path}: redirects to ${target}, expected ${entry.target}`);
    } else if (entry.expect === "page") {
      if (target) failures.push(`${entry.path}: expected page, got redirect → ${target}`);
    } else if (entry.expect === "file") {
      if (entry.contains && !body.includes(entry.contains))
        failures.push(`${entry.path}: does not contain ${JSON.stringify(entry.contains)}`);
    }
  }
  return failures;
}

// ---------------------------------------------------------------- main

const args = process.argv.slice(2);
const opt = (name) => {
  const i = args.indexOf(name);
  return i === -1 ? null : args[i + 1];
};
const buildDir = args[0] && !args[0].startsWith("--") ? args[0] : null;
const comparePath = opt("--compare");
const fixturePath = opt("--fixture");
const host = opt("--host");

if (fixturePath) {
  const all = JSON.parse(readFileSync(fixturePath, "utf8"));
  const prMode = args.includes("--pr-mode");
  const fixture = prMode ? all.filter((e) => !e.fullBuildOnly) : all;
  if (prMode && fixture.length < all.length)
    console.log(`docs-parity: --pr-mode skipping ${all.length - fixture.length} full-build-only entries.`);
  const failures = host
    ? await runFixtureLive(fixture, host)
    : await runFixtureStatic(fixture, buildDir ?? fail("need build dir or --host"));
  const total = fixture.length;
  if (failures.length) {
    for (const f of failures) console.error(`FIXTURE FAIL  ${f}`);
    console.error(`docs-parity: fixture ${total - failures.length}/${total} passed.`);
    process.exit(1);
  }
  console.log(`docs-parity: fixture ${total}/${total} passed.`);
} else if (comparePath) {
  compare(buildManifest(buildDir ?? fail("need build dir")), comparePath);
} else if (buildDir) {
  console.log(JSON.stringify(buildManifest(buildDir), null, 2));
} else {
  fail("usage: docs-parity.mjs <buildDir> [--compare baseline.json] [--fixture fixture.json] | --host <origin> --fixture fixture.json");
}
