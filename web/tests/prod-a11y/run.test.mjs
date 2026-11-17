/** Launcher contracts only: no real Playwright, browser, hub or network. */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import test from "node:test";

function fixture(t, { installCli = true } = {}) {
  const root = mkdtempSync(path.join(tmpdir(), "prod-a11y-launcher-"));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  const web = path.join(root, "web");
  const launcher = path.join(web, "tests", "prod-a11y", "run.mjs");
  const cli = path.join(web, "node_modules", "@playwright", "test", "cli.js");
  const artifactRoot = path.join(root, "artifacts");
  const runId = "prod-a11y-launcher-contract";
  const runDir = path.join(artifactRoot, runId);
  const invocation = path.join(root, "child-invocation.json");
  mkdirSync(path.dirname(launcher), { recursive: true });
  copyFileSync(new URL("./run.mjs", import.meta.url), launcher);
  if (installCli) {
    mkdirSync(path.dirname(cli), { recursive: true });
    writeFileSync(path.join(path.dirname(cli), "package.json"), JSON.stringify({ type: "module" }));
    // Deliberately model Playwright's destructive output cleanup. A duplicate
    // run must be refused before this process gets any opportunity to execute.
    writeFileSync(
      cli,
      `import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
const runDir = path.join(process.env.AUDIT_ARTIFACT_DIR, process.env.AUDIT_RUN_ID);
writeFileSync(process.env.FIXTURE_INVOCATION, JSON.stringify({
  args: process.argv.slice(2),
  cwd: process.cwd(),
  token: process.env.AUDIT_RUN_TOKEN,
  owner: readFileSync(path.join(runDir, ".run-owner"), "utf8"),
  runner: JSON.parse(readFileSync(path.join(runDir, "runner.json"), "utf8")),
}));
rmSync(path.join(runDir, "results"), { recursive: true, force: true });
mkdirSync(path.join(runDir, "results"));
writeFileSync(path.join(runDir, "results", "child-evidence.txt"), "synthetic child evidence");
writeFileSync(path.join(runDir, "report.json"), "synthetic replacement report");
if (process.env.FIXTURE_SIGNAL === "yes") process.kill(process.pid, "SIGTERM");
else process.exitCode = Number(process.env.FIXTURE_EXIT_CODE ?? "0");
`,
    );
  }
  return {
    web,
    artifactRoot,
    runDir,
    invocation,
    run(args = [], overrides = {}) {
      const result = spawnSync(process.execPath, [launcher, ...args], {
        cwd: root,
        encoding: "utf8",
        timeout: 10000,
        env: {
          ...process.env,
          AUDIT_ARTIFACT_DIR: artifactRoot,
          AUDIT_RUN_ID: runId,
          AUDIT_RUN_TOKEN: "inherited-token-must-not-be-reused",
          FIXTURE_INVOCATION: invocation,
          FIXTURE_EXIT_CODE: "0",
          FIXTURE_SIGNAL: "no",
          ...overrides,
        },
      });
      assert.ifError(result.error);
      assert.equal(result.signal, null, result.stderr);
      return result;
    },
  };
}

function readJson(file) {
  return JSON.parse(readFileSync(file, "utf8"));
}

function snapshot(directory) {
  return readdirSync(directory, { withFileTypes: true })
    .sort((left, right) => left.name.localeCompare(right.name))
    .map((entry) => {
      const file = path.join(directory, entry.name);
      return [entry.name, entry.isDirectory() ? snapshot(file) : readFileSync(file)];
    });
}

test("reusing a run ID preserves every existing evidence byte and never starts the child", (t) => {
  const f = fixture(t);
  mkdirSync(path.join(f.runDir, "results", "passed-state"), { recursive: true });
  writeFileSync(path.join(f.runDir, ".run-owner"), "original-owner");
  writeFileSync(path.join(f.runDir, "runner.json"), '{"startedAt":"original"}\n');
  writeFileSync(path.join(f.runDir, "runner-result.json"), '{"exitCode":17}\n');
  writeFileSync(path.join(f.runDir, "report.json"), '{"violations":["preserve this finding"]}\n');
  writeFileSync(path.join(f.runDir, "results", "passed-state", "trace.zip"), Buffer.from([0, 255, 80, 75, 13, 10]));
  const before = snapshot(f.runDir);

  const result = f.run(["--project=desktop-light", "--grep=empty-pages"]);

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Evidence already exists/);
  assert.equal(existsSync(f.invocation), false);
  assert.deepEqual(snapshot(f.runDir), before);
});

test("a fresh run reserves its evidence before invoking the fixed one-worker survey", (t) => {
  const f = fixture(t);
  const filters = ["--project=desktop-light", "--grep", "empty-pages", "--grep-invert=synthetic-panel", "--list"];
  const result = f.run(filters);

  assert.equal(result.status, 0, result.stderr);
  const child = readJson(f.invocation);
  assert.deepEqual(child.args, [
    "test",
    "--config",
    path.join(f.web, "tests", "prod-a11y", "playwright.config.ts"),
    "routes.audit.ts",
    "--workers=1",
    ...filters,
  ]);
  assert.equal(child.cwd, f.web);
  assert.ok(child.token.length > 0);
  assert.notEqual(child.token, "inherited-token-must-not-be-reused");
  assert.equal(child.token, child.owner);
  assert.equal(statSync(path.join(f.runDir, ".run-owner")).mode & 0o777, 0o600);
  assert.equal(child.runner.runId, path.basename(f.runDir));
  assert.deepEqual(child.runner.args, filters);
  assert.equal(child.runner.listingOnly, true);
  assert.ok(Number.isFinite(Date.parse(child.runner.startedAt)));
  const receipt = readJson(path.join(f.runDir, "runner-result.json"));
  assert.equal(receipt.exitCode, 0);
  assert.equal(receipt.signal, null);
  assert.ok(Number.isFinite(Date.parse(receipt.finishedAt)));
  assert.equal(readFileSync(path.join(f.runDir, "results", "child-evidence.txt"), "utf8"), "synthetic child evidence");
});

test("child failure is returned and a retry cannot replace its evidence or failure receipt", (t) => {
  const f = fixture(t);
  const result = f.run([], { FIXTURE_EXIT_CODE: "17" });

  assert.equal(result.status, 17, result.stderr);
  const receipt = readJson(path.join(f.runDir, "runner-result.json"));
  assert.equal(receipt.exitCode, 17);
  assert.equal(receipt.signal, null);
  assert.equal(readJson(f.invocation).runner.listingOnly, false);
  const before = snapshot(f.runDir);
  rmSync(f.invocation);

  const retry = f.run();

  assert.notEqual(retry.status, 0);
  assert.match(retry.stderr, /Evidence already exists/);
  assert.equal(existsSync(f.invocation), false);
  assert.deepEqual(snapshot(f.runDir), before);
});

test("a child terminated by a signal records that signal and makes the launcher fail", (t) => {
  const f = fixture(t);
  const result = f.run([], { FIXTURE_SIGNAL: "yes" });

  assert.equal(result.status, 1, result.stderr);
  const receipt = readJson(path.join(f.runDir, "runner-result.json"));
  assert.equal(receipt.exitCode, null);
  assert.equal(receipt.signal, "SIGTERM");
  assert.equal(readFileSync(path.join(f.runDir, "results", "child-evidence.txt"), "utf8"), "synthetic child evidence");
});

test("caller arguments cannot override the spec, config, workers or evidence destinations", async (t) => {
  for (const args of [
    ["--workers=2"],
    ["--config", "other.config.ts"],
    ["--output=/tmp/other-evidence"],
    ["--reporter=line"],
    ["--repeat-each=2"],
    ["other.spec.ts"],
    ["--project", "--workers=2"],
    ["--grep="],
  ]) {
    await t.test(args.join(" "), (subtest) => {
      const f = fixture(subtest);
      const result = f.run(args);

      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /Unsupported audit argument/);
      assert.equal(existsSync(f.invocation), false);
      assert.equal(existsSync(f.artifactRoot), false);
    });
  }
});

test("invalid artifact paths and run IDs fail without starting the child or reserving a run", async (t) => {
  for (const overrides of [
    { AUDIT_ARTIFACT_DIR: "relative-artifacts" },
    { AUDIT_ARTIFACT_DIR: "" },
    { AUDIT_RUN_ID: "prod-a11y-../existing" },
    { AUDIT_RUN_ID: "" },
  ]) {
    await t.test(JSON.stringify(overrides), (subtest) => {
      const f = fixture(subtest);
      const result = f.run([], overrides);

      assert.notEqual(result.status, 0);
      assert.match(result.stderr, /Set an absolute AUDIT_ARTIFACT_DIR/);
      assert.equal(existsSync(f.invocation), false);
      assert.equal(existsSync(f.artifactRoot), false);
    });
  }
});

test("missing Playwright dependencies do not leave a reserved evidence directory", (t) => {
  const f = fixture(t, { installCli: false });
  const result = f.run();

  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Install the locked web dependencies/);
  assert.equal(existsSync(f.invocation), false);
  assert.equal(existsSync(f.artifactRoot), false);
});
