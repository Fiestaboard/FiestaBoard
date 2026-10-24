import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { readFileSync } from "node:fs";
import http from "node:http";
import net from "node:net";
import test from "node:test";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";

const webRoot = fileURLToPath(new URL("../", import.meta.url));

function request(port, host) {
  return new Promise((resolve, reject) => {
    // fetch may replace Host; use raw HTTP to exercise the server's allowlist.
    const req = http.get(
      { hostname: "127.0.0.1", port, path: "/index.json", headers: { Host: `${host}:${port}` } },
      (res) => {
        res.resume();
        resolve(res.statusCode);
      },
    );
    req.setTimeout(2000, () => req.destroy(new Error("Storybook request timed out")));
    req.on("error", reject);
  });
}

test("Docker Storybook keeps host validation enabled", { timeout: 90000 }, async (t) => {
  // Never launch a server affected by the October 2026 advisories, even if a
  // later dependency change accidentally restores an affected lockfile.
  const { version } = JSON.parse(readFileSync(new URL("../node_modules/storybook/package.json", import.meta.url)));
  const [major, minor, patch] = version.split(".").map(Number);
  assert.ok(
    /^\d+\.\d+\.\d+$/.test(version) && (major > 10 || (major === 10 && (minor > 6 || (minor === 6 && patch >= 2)))),
    `Refusing to launch unverified Storybook ${version}; use a patched stable release`,
  );

  const reservation = net.createServer();
  reservation.listen(0, "127.0.0.1");
  await once(reservation, "listening");
  const { port } = reservation.address();
  await new Promise((resolve) => reservation.close(resolve));

  // Match the Docker profile's wildcard bind, without publishing a host port.
  const child = spawn(
    process.execPath,
    [
      "node_modules/.bin/storybook",
      "dev",
      "--host",
      "0.0.0.0",
      "--port",
      String(port),
      "--exact-port",
      "--ci",
      "--no-open",
      "--disable-telemetry",
    ],
    { cwd: webRoot, detached: true, stdio: ["ignore", "pipe", "pipe"] },
  );
  let output = "";
  for (const stream of [child.stdout, child.stderr]) {
    stream.on("data", (chunk) => (output = (output + chunk).slice(-32000)));
  }
  const exited = once(child, "exit");
  t.after(async () => {
    if (child.exitCode !== null || child.signalCode !== null) return;
    process.kill(-child.pid, "SIGTERM");
    if (!(await Promise.race([exited.then(() => true), delay(5000, undefined, { ref: false }).then(() => false)]))) {
      process.kill(-child.pid, "SIGKILL");
      await exited;
    }
  });

  let ready = false;
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    assert.equal(child.exitCode, null, `Storybook exited before readiness:\n${output}`);
    try {
      ready = (await request(port, "localhost")) === 200;
    } catch {
      // The server has not bound yet.
    }
    if (ready) break;
    await delay(250);
  }
  assert.ok(ready, `Storybook did not become ready:\n${output}`);

  for (const [host, expected] of [
    ["localhost", 200],
    ["127.0.0.1", 200],
    ["untrusted.example", 403],
    ["localhost.untrusted.example", 403],
  ]) {
    await t.test(`${host} returns ${expected}`, async () => {
      assert.equal(await request(port, host), expected);
    });
  }
});
