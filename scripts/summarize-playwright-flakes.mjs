#!/usr/bin/env node
/**
 * Surface Playwright tests that only passed because of a retry.
 *
 * `retries: 1` means a flaky test reports "1 flaky" in the log and the job
 * still goes green, so nobody sees it. This reads the JSON reporter's output
 * and turns each flaky spec into a GitHub annotation plus a row in the job
 * summary, giving flakes a durable, greppable record before the suite grows.
 *
 * Usage: node scripts/summarize-playwright-flakes.mjs <report.json> [label]
 *
 * Always exits 0 — a flake is a signal to act on, not a reason to fail a job
 * that Playwright already decided had passed.
 */
import { appendFileSync, readFileSync } from "node:fs";
import { isAbsolute, relative } from "node:path";

const [reportPath, label = "e2e"] = process.argv.slice(2);

if (!reportPath) {
  console.error("usage: summarize-playwright-flakes.mjs <report.json> [label]");
  process.exit(0);
}

let report;
try {
  report = JSON.parse(readFileSync(reportPath, "utf8"));
} catch (err) {
  // A missing report means the run died before the reporter flushed (container
  // never came up, step timeout). That is already loud elsewhere; don't add
  // a second confusing failure here.
  console.log(`[flakes] no readable report at ${reportPath}: ${err.message}`);
  process.exit(0);
}

/**
 * Spec `file` paths in the report are relative to `config.rootDir` (the
 * resolved testDir), so they need a prefix before a GitHub annotation can
 * anchor to them. In CI this step runs from the repo root and the relative
 * path resolves exactly.
 */
function repoRelativeTestDir(rootDir) {
  if (!rootDir) return "web/tests";
  const rel = relative(process.cwd(), rootDir);
  if (rel && !rel.startsWith("..") && !isAbsolute(rel)) return rel;
  // Path mismatch — e.g. Playwright ran inside a container with the repo
  // mounted at a different root. Recover the tail from the last `web/`.
  const m = rootDir.match(/(?:^|\/)(web\/.*)$/);
  return m ? m[1] : "web/tests";
}

/**
 * Playwright puts ANSI colour codes in error messages; they are noise in an
 * annotation. The ESC byte has to be part of the pattern — matching only
 * `\[[0-9;]*m` leaves the ESC behind (invisible in a terminal, still in the
 * string) and eats plain text like `array[2m]`.
 */
// eslint-disable-next-line no-control-regex
const ANSI = /\u001b\[[0-9;]*m/g;

/** Walk the nested suite tree and yield every spec with its owning file. */
function* walkSpecs(suite, file) {
  const currentFile = suite.file || file;
  for (const spec of suite.specs ?? []) {
    yield { spec, file: spec.file || currentFile };
  }
  for (const child of suite.suites ?? []) {
    yield* walkSpecs(child, currentFile);
  }
}

const testDir = repoRelativeTestDir(report.config?.rootDir);

const flaky = [];
for (const suite of report.suites ?? []) {
  for (const { spec, file } of walkSpecs(suite)) {
    for (const test of spec.tests ?? []) {
      if (test.status !== "flaky") continue;
      const failed = (test.results ?? []).find((r) => r.status !== "passed");
      flaky.push({
        title: spec.title,
        file: file ? `${testDir}/${file}` : testDir,
        line: spec.line,
        attempts: (test.results ?? []).length,
        error: (failed?.error?.message ?? "")
          .replace(ANSI, "")
          .split("\n")[0]
          .slice(0, 200)
          .trim(),
      });
    }
  }
}

if (flaky.length === 0) {
  console.log(`[flakes] ${label}: none`);
  process.exit(0);
}

for (const f of flaky) {
  // `::warning file=…` puts the flake on the PR diff next to the test.
  console.log(`::warning file=${f.file},line=${f.line}::Flaky (${label}): ${f.title} — ${f.error}`);
}

const summary = process.env.GITHUB_STEP_SUMMARY;
if (summary) {
  // A `|` anywhere in a cell splits the markdown row, and test titles contain
  // them at least as often as error messages do. Backslashes have to be
  // escaped *first*: escaping only the pipe turns an input `\|` into `\\|`,
  // an escaped backslash followed by a live pipe, which still breaks the row.
  // A newline ends the row outright, so flatten those too.
  const cell = (s) =>
    String(s)
      .replace(/\\/g, "\\\\")
      .replace(/\|/g, "\\|")
      .replace(/\r?\n/g, " ");
  const rows = flaky
    .map((f) => `| \`${cell(f.file)}:${f.line}\` | ${cell(f.title)} | ${f.attempts} | ${cell(f.error)} |`)
    .join("\n");
  appendFileSync(
    summary,
    `\n### ⚠️ Flaky tests (${label}): ${flaky.length}\n\n` +
      `These passed only on retry. The job is green; the flake is not.\n\n` +
      `| Spec | Test | Attempts | First failure |\n|---|---|---|---|\n${rows}\n`,
  );
}

console.log(`[flakes] ${label}: ${flaky.length} test(s) passed only on retry`);
