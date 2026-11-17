import http from "node:http";
import https from "node:https";
import { lstat, readFile } from "node:fs/promises";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import { redact, validateBatchTiming, validateSessionBatch, validateSessionCookieHeaders } from "./web_protocol.mjs";

// Browser runner entry point. No side effects on import; root owns execution.
export async function readPrivateCredentials(path) {
  const info = await lstat(path);
  if (!info.isFile() || info.isSymbolicLink()) throw new Error("Private credentials must be a regular file, never a symlink");
  if ((info.mode & 0o777) !== 0o600) throw new Error("Private credentials require mode0600 permissions");
  let value;
  try {
    value = JSON.parse(await readFile(path, "utf8"));
  } catch {
    throw new Error("Private credential JSON could not be read/parsed");
  }
  if (!value || typeof value.username !== "string" || !value.username || typeof value.password !== "string" || value.password.length < 8) throw new Error("Synthetic credential fields are invalid");
  return { username: value.username, password: value.password };
}

export async function loadRunConfig(path) {
  let value;
  try {
    value = JSON.parse(await readFile(path, "utf8"));
  } catch {
    throw new Error("Run config JSON could not be read/parsed");
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Run config must be a JSON object");
  return value;
}

export async function verifyFixtureThroughSession({ manifest, origin, session, apiHarnessDir, timeoutMs = 300000, maxRequests = 200, maxFrameBytes = 4 * 1024 * 1024, pythonExecutable = "python3", onRecord = () => {} }) {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || !Number.isInteger(maxRequests) || maxRequests < 1 || !Number.isInteger(maxFrameBytes) || maxFrameBytes < 256) throw new Error("Verifier request/frame/deadline bounds are required");
  const flags = ["exact_counts", "exact_ids", "geometry", "read_back", "runtime_manual_state"];
  const controller = new AbortController();
  const safeEnvironment = Object.fromEntries(["PATH", "LANG", "LC_ALL", "TZ"].filter((key) => process.env[key]).map((key) => [key, process.env[key]]));
  const child = spawn(pythonExecutable, ["-I", "-B", fileURLToPath(new URL("./web_verify_bridge.py", import.meta.url)), "--api-harness-dir", apiHarnessDir, "--max-frame-bytes", String(maxFrameBytes)], { stdio: ["pipe", "pipe", "pipe"], env: safeEnvironment });
  let processError;
  let timedOut = false;
  let requestCount = 0;
  let result;
  let stderrBytes = 0;
  child.once("error", (error) => { processError = error; });
  child.stdin.on("error", () => {});
  child.stderr.on("data", (chunk) => { stderrBytes = Math.min(stderrBytes + chunk.length, maxFrameBytes); });
  const closed = new Promise((resolve) => child.once("close", (code, signal) => resolve({ code, signal })));
  const writeFrame = async (frame) => {
    const bytes = Buffer.from(`${JSON.stringify(frame)}\n`);
    if (bytes.length > maxFrameBytes) throw new Error("Verifier IPC frame exceeds size limit");
    await new Promise((resolve, reject) => child.stdin.write(bytes, (error) => error ? reject(error) : resolve()));
  };
  const handle = async (frame) => {
    if (result) throw new Error("Verifier emitted data after its terminal result");
    if (frame.type === "request") {
      if (frame.method !== "GET" || typeof frame.path !== "string" || !frame.path.startsWith("/api/") || new URL(frame.path, origin).origin !== new URL(origin).origin || new URL(frame.path, origin).hash) throw new Error("Read-only verifier only permits same-origin GET requests");
      if (requestCount >= maxRequests) throw new Error("Verifier request limit exceeded");
      requestCount += 1;
      if (frame.id !== requestCount) throw new Error("Verifier request sequence is not serial");
      const body = await session.getJson(frame.path, { signal: controller.signal });
      await writeFrame({ type: "response", id: frame.id, status: 200, body });
    } else if (frame.type === "result") {
      if (requestCount === 0 || !flags.every((key) => frame.verification?.[key] === true)) throw new Error("Verifier result is incomplete or has no actual reads");
      result = Object.fromEntries(flags.map((key) => [key, true]));
    } else throw new Error(`Read-only verifier child failed: ${typeof frame.error_type === "string" ? frame.error_type : "invalid frame"}`);
  };
  let timer;
  const deadline = new Promise((_resolve, reject) => {
    timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
      child.kill("SIGTERM");
      reject(new Error("Verifier overall deadline exceeded"));
    }, timeoutMs);
  });
  const work = async () => {
    await writeFrame({ origin, manifest });
    let pending = Buffer.alloc(0);
    for await (const chunk of child.stdout) {
      pending = Buffer.concat([pending, chunk]);
      if (pending.length > maxFrameBytes) throw new Error("Verifier stdout frame exceeds size limit");
      let newline;
      while ((newline = pending.indexOf(10)) !== -1) {
        const line = pending.subarray(0, newline);
        pending = pending.subarray(newline + 1);
        let frame;
        try { frame = JSON.parse(line.toString()); } catch { throw new Error("Verifier emitted invalid JSON frame"); }
        await handle(frame);
      }
    }
    if (pending.length) throw new Error("Verifier child ended with a partial JSON frame");
    const exit = await closed;
    if (processError || exit.code !== 0 || !result) throw new Error(`Verifier child exited without complete verification (code${exit.code})`);
    onRecord({ record_type: "fixture_verification", verification: result, request_count: requestCount, stderr_bytes: stderrBytes, timed: false });
    return result;
  };
  try {
    return await Promise.race([work(), deadline]);
  } catch (error) {
    onRecord({ record_type: "fixture_verification", complete: false, request_count: requestCount, error: timedOut ? "overall_deadline" : "verifier_failed", stderr_bytes: stderrBytes, timed: false });
    throw timedOut ? new Error("Verifier overall deadline exceeded") : error;
  } finally {
    clearTimeout(timer);
    controller.abort();
    child.stdin.destroy();
    if (child.exitCode === null && child.signalCode === null) child.kill("SIGTERM");
    const killTimer = setTimeout(() => child.kill("SIGKILL"), 1000);
    await closed;
    clearTimeout(killTimer);
  }
}

export async function createBatchSession({ origin, credentials, userAgent, clock = () => new Date().toISOString(), batchSeconds, marginSeconds, expectedCount, timeoutMs = 10000, onRecord = () => {} }) {
  const base = new URL(origin);
  if (!["http:", "https:"].includes(base.protocol) || base.username || base.password || base.pathname !== "/" || base.search || base.hash) throw new Error("Batch authentication requires one credential-free origin");
  if (!credentials?.username || !credentials.password || !userAgent?.startsWith("Mozilla/")) throw new Error("Private credentials and a pinned browser User-Agent are required");
  const secrets = [credentials.password];
  const timing = { batchSeconds, marginSeconds, expectedCount };
  if (typeof clock !== "function" || !Number.isFinite(timeoutMs) || timeoutMs <= 0) throw new Error("Batch clock and request timeout must be valid before login");
  validateBatchTiming({ ...timing, nowUtc: clock() });
  let cookieHeader;
  let cookieValue;
  let cookieFlags;
  let metadata;
  let aborted = false;
  const transport = base.protocol === "https:" ? https : http;
  const jsonRequest = async (path, { method = "GET", data, signal } = {}) => {
    if (typeof path !== "string" || !path.startsWith("/api/") || new URL(path, base).origin !== base.origin) throw new Error("A batch cookie may only reach its declared same-origin API");
    const body = data === undefined ? undefined : Buffer.from(JSON.stringify(data));
    const headers = { Accept: "application/json", "Accept-Encoding": "identity", "User-Agent": userAgent };
    if (body) Object.assign(headers, { "Content-Type": "application/json", "Content-Length": body.length });
    if (cookieHeader) headers.Cookie = cookieHeader;
    let timer;
    let response;
    try {
      response = await new Promise((resolve, reject) => {
        const request = transport.request(new URL(path, base), { method, headers, agent: false, signal }, (incoming) => {
          const chunks = [];
          incoming.on("data", (chunk) => chunks.push(chunk));
          incoming.once("error", reject);
          incoming.once("end", () => resolve({ status: incoming.statusCode, headers: incoming.headers, body: Buffer.concat(chunks) }));
        });
        timer = setTimeout(() => request.destroy(new Error("Authentication/API request deadline")), timeoutMs);
        request.once("error", reject);
        request.end(body);
      });
    } catch (error) {
      onRecord(redact({ record_type: "browser_auth", path, method, status: null, error: String(error), timed: false }, secrets));
      throw new Error(`Batch API transport failed: ${redact(String(error), secrets)}`);
    } finally {
      clearTimeout(timer);
    }
    for (const value of response.headers["set-cookie"] ?? []) {
      const match = /^fiestaboard_session=([^;]+)/.exec(value);
      if (match) secrets.push(match[1]);
    }
    let parsed;
    try {
      if (response.headers["content-encoding"] && response.headers["content-encoding"] !== "identity") throw new Error("Unexpected encoded API response");
      parsed = JSON.parse(response.body.toString());
    } catch {
      onRecord(redact({ record_type: "browser_auth", path, method, status: response.status, bytes: response.body.length, error: "invalid_json_or_encoding", timed: false }, secrets));
      throw new Error(`Invalid JSON/encoding from batch API at ${path}`);
    }
    onRecord(redact({ record_type: "browser_auth", path, method, status: response.status, bytes: response.body.length, response: parsed, headers: response.headers, timed: false }, secrets));
    return { ...response, json: parsed };
  };
  const getJson = async (path, { signal } = {}) => {
    if (aborted) throw new Error("Authentication batch was aborted; no retry or relogin allowed");
    const response = await jsonRequest(path, { signal });
    if (response.status === 401) {
      aborted = true;
      throw new Error("Protected API returned 401; authentication batch aborted");
    }
    if (response.status !== 200) throw new Error(`Protected API returned ${response.status} at ${path}`);
    return response.json;
  };
  const status = await getJson("/api/auth/status");
  if (status.enabled !== true || status.setup_required !== false) throw new Error("Batch target store must already be provisioned with real authentication");
  const login = await jsonRequest("/api/auth/login", { method: "POST", data: { username: credentials.username, password: credentials.password, remember_me: false } });
  if (login.status !== 200 || login.json.status !== "ok" || login.json.username !== credentials.username) throw new Error(`Real browser login failed with status ${login.status}`);
  cookieFlags = validateSessionCookieHeaders(login.headers["set-cookie"] ?? []);
  const genuine = login.headers["set-cookie"].find((value) => value.startsWith("fiestaboard_session="));
  cookieValue = /^fiestaboard_session=([^;]+)/.exec(genuine)?.[1];
  if (!cookieValue) throw new Error("Real login did not return a session cookie");
  cookieHeader = `fiestaboard_session=${cookieValue}`;
  const authenticated = await getJson("/api/auth/status");
  if (authenticated.enabled !== true || authenticated.authenticated !== true || authenticated.auth_kind !== "browser" || authenticated.setup_required !== false) throw new Error("Real browser cookie authentication was not verified");
  const verifySession = async () => {
    const snapshot = await getJson("/api/auth/sessions");
    metadata = validateSessionBatch(snapshot, { ...timing, nowUtc: clock(), expectedCount: metadata?.session_count ?? expectedCount });
    return { ...metadata };
  };
  await verifySession();
  return {
    getJson, verifySession,
    metadata: () => ({ ...metadata, cookie_flags: { ...cookieFlags } }),
    cookiesForContext: () => [{ name: "fiestaboard_session", value: cookieValue, domain: base.hostname, path: "/", httpOnly: true, secure: cookieFlags.secure, sameSite: "Lax" }],
    toJSON: () => ({ ...metadata, cookie_flags: { ...cookieFlags } }),
  };
}

export async function runBrowserBatch(config) {
  if (!config?.manifest || typeof config.manifest !== "object") throw new Error("A verified public manifest is required");
  throw new Error("Browser execution is not implemented; no measurement is complete");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  if (process.argv.length !== 4 || process.argv[2] !== "--config") {
    process.stderr.write("Usage: node web_run.mjs --config <private-run-config.json>\n");
    process.exitCode = 2;
  } else {
    try {
      const config = await loadRunConfig(process.argv[3]);
      await runBrowserBatch(config);
    } catch (error) {
      process.stderr.write(`Browser run refused: ${error.message}\n`);
      process.exitCode = 1;
    }
  }
}
