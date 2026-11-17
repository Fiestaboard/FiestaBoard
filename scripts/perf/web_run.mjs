import http from "node:http";
import https from "node:https";
import { fileURLToPath } from "node:url";

import { redact, validateSessionBatch, validateSessionCookieHeaders } from "./web_protocol.mjs";

// Browser runner entry point. No side effects on import; root owns execution.
export async function createBatchSession({ origin, credentials, userAgent, nowUtc, batchSeconds, marginSeconds, expectedCount, timeoutMs = 10000, onRecord = () => {} }) {
  const base = new URL(origin);
  if (!["http:", "https:"].includes(base.protocol) || base.username || base.password || base.pathname !== "/" || base.search || base.hash) throw new Error("Batch authentication requires one credential-free origin");
  if (!credentials?.username || !credentials.password || !userAgent?.startsWith("Mozilla/")) throw new Error("Private credentials and a pinned browser User-Agent are required");
  const secrets = [credentials.password];
  const timing = { nowUtc, batchSeconds, marginSeconds, expectedCount };
  let cookieHeader;
  let cookieValue;
  let cookieFlags;
  let metadata;
  let aborted = false;
  const transport = base.protocol === "https:" ? https : http;
  const jsonRequest = async (path, { method = "GET", data } = {}) => {
    if (typeof path !== "string" || !path.startsWith("/api/") || new URL(path, base).origin !== base.origin) throw new Error("A batch cookie may only reach its declared same-origin API");
    const body = data === undefined ? undefined : Buffer.from(JSON.stringify(data));
    const headers = { Accept: "application/json", "Accept-Encoding": "identity", "User-Agent": userAgent };
    if (body) Object.assign(headers, { "Content-Type": "application/json", "Content-Length": body.length });
    if (cookieHeader) headers.Cookie = cookieHeader;
    let timer;
    let response;
    try {
      response = await new Promise((resolve, reject) => {
        const request = transport.request(new URL(path, base), { method, headers, agent: false }, (incoming) => {
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
  const getJson = async (path) => {
    if (aborted) throw new Error("Authentication batch was aborted; no retry or relogin allowed");
    const response = await jsonRequest(path);
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
    metadata = validateSessionBatch(snapshot, { ...timing, expectedCount: metadata?.session_count ?? expectedCount });
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
  process.stderr.write("Usage: node web_run.mjs --config <private-run-config.json>; browser execution is not implemented yet.\n");
  process.exitCode = 2;
}
