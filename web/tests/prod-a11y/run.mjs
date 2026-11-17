/** Explicit audit entry point; run inside the approved browser container. */
import { spawnSync } from "node:child_process";
import { randomUUID } from "node:crypto";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const artifactRoot = process.env.AUDIT_ARTIFACT_DIR;
const runId = process.env.AUDIT_RUN_ID;
if (!artifactRoot || !path.isAbsolute(artifactRoot) || !/^prod-a11y-[a-z0-9-]+$/.test(runId ?? "")) {
  throw new Error("Set an absolute AUDIT_ARTIFACT_DIR and a unique prod-a11y-... AUDIT_RUN_ID.");
}

// Keep the single-spec, one-worker config and evidence destinations immutable.
// Filtering projects/cases or listing them is useful for bounded first runs.
const args = process.argv.slice(2);
for (let index = 0; index < args.length; index += 1) {
  const arg = args[index];
  if (arg === "--list" || /^--(project|grep|grep-invert)=.+$/.test(arg)) continue;
  if (
    ["--project", "--grep", "--grep-invert"].includes(arg) &&
    args[index + 1] &&
    !args[index + 1].startsWith("--")
  ) {
    index += 1;
    continue;
  }
  throw new Error(`Unsupported audit argument: ${arg}. Use only --project, --grep, --grep-invert or --list.`);
}

const cli = fileURLToPath(new URL("../../node_modules/@playwright/test/cli.js", import.meta.url));
if (!existsSync(cli)) throw new Error("Install the locked web dependencies in the approved container first.");

const runDir = path.join(artifactRoot, runId);
mkdirSync(artifactRoot, { recursive: true });
try {
  // Exclusive mkdir happens BEFORE Playwright starts, loads its config or clears
  // outputDir. Never delete/reuse a failed run: choose a new run ID for a retry.
  mkdirSync(runDir);
} catch (error) {
  if (error.code === "EEXIST") throw new Error(`Evidence already exists at ${runDir}; choose a new AUDIT_RUN_ID.`);
  throw error;
}
const token = randomUUID();
writeFileSync(path.join(runDir, ".run-owner"), token, { flag: "wx", mode: 0o600 });
writeFileSync(
  path.join(runDir, "runner.json"),
  JSON.stringify({ startedAt: new Date().toISOString(), runId, args, listingOnly: args.includes("--list") }, null, 2),
  { flag: "wx" },
);

const result = spawnSync(
  process.execPath,
  [
    cli,
    "test",
    "--config",
    fileURLToPath(new URL("./playwright.config.ts", import.meta.url)),
    "routes.audit.ts",
    "--workers=1",
    ...args,
  ],
  {
    cwd: fileURLToPath(new URL("../../", import.meta.url)),
    stdio: "inherit",
    env: { ...process.env, AUDIT_RUN_TOKEN: token },
  },
);
writeFileSync(
  path.join(runDir, "runner-result.json"),
  JSON.stringify(
    { finishedAt: new Date().toISOString(), exitCode: result.status, signal: result.signal, error: result.error?.message },
    null,
    2,
  ),
  { flag: "wx" },
);
process.exitCode = result.status ?? 1;
