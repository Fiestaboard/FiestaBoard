import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { chmod, lstat, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { gzipSync } from "node:zlib";
import { test } from "node:test";
import vm from "node:vm";

import { buildCollectorInitScript, collectorMetadataFromProvenance, createRelay, installBrowserCollector, planBrowserBatch, profileFor, redact, relayLocation, relayRequestHeaders, summarizeMetrics, validateDocumentObservation, validateEffectiveBrowser, validateRunEvidence, validateRuntimeBinding, validateSessionBatch, validateSessionCookieHeaders, verifyCollector } from "./web_protocol.mjs";
import { applyBrowserProfile, collectBatchSamples, createBatchSession, createObservationWriter, launchOwnedChromium, loadRunConfig, readPrivateCredentials, runBrowserBatch, verifyFixtureThroughSession } from "./web_run.mjs";

// These controlled loopback servers run only when root executes this test in
// its serialized shared role. They never start the app or contact a live hub.
async function upstream(t, handler) {
  const server = http.createServer(handler);
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  t.after(() => new Promise((resolve) => server.close(resolve)));
  return `http://127.0.0.1:${server.address().port}`;
}

function request(url, { method = "GET", headers = {}, body } = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(url, { method, headers, agent: false }, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.once("error", reject);
      res.once("end", () => resolve({ status: res.statusCode, headers: res.headers, body: Buffer.concat(chunks) }));
    });
    req.setTimeout(2000, () => req.destroy(new Error("test request deadline")));
    req.once("error", reject);
    req.end(body);
  });
}

async function relayFor(t, targetUrl) {
  const relay = await createRelay({ targetUrl, requestTimeoutMs: 1000 });
  assert.ok(relay && typeof relay.origin === "string", "relay exposes its actual loopback origin");
  assert.equal(new URL(relay.origin).hostname, "127.0.0.1");
  t.after(() => relay.close());
  return relay;
}

test("decimal Mbit profiles reach CDP as bytes per second rather than bits or binary megabytes", () => {
  assert.deepEqual(profileFor("desktop"), {
    viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, isMobile: false, hasTouch: false,
    cpuThrottlingRate: 1,
    network: { offline: false, latency: 20, downloadThroughput: 2500000, uploadThroughput: 1250000 },
  });
  assert.deepEqual(profileFor("phone"), {
    viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true,
    cpuThrottlingRate: 4,
    network: { offline: false, latency: 150, downloadThroughput: 200000, uploadThroughput: 93750 },
  });
  assert.throws(() => profileFor("unknown"), /profile/i);
});

test("final metric IDs from another document cannot satisfy this document's completeness", () => {
  const result = summarizeMetrics([
    { document_id: "old", name: "LCP", id: "same-id", value: 1, final: true },
    { document_id: "old", name: "INP", id: "old-inp", value: 1, final: true },
    { document_id: "current", name: "LCP", id: "same-id", value: 432, final: true },
  ], { documentId: "current", hiddenObserved: true, inputVerified: true });
  assert.equal(result.complete, false);
  assert.deepEqual(result.metrics, { LCP: { id: "same-id", value: 432 }, INP: null });
  assert.deepEqual(result.missing, ["INP"]);
});

test("intermediate metrics never become fabricated final values when the final callback is missing", () => {
  const result = summarizeMetrics([
    { document_id: "d1", name: "LCP", id: "l1", value: 270, final: false },
    { document_id: "d1", name: "INP", id: "i1", value: 18, final: false },
  ], { documentId: "d1", hiddenObserved: true, inputVerified: true });
  assert.equal(result.complete, false);
  assert.deepEqual(result.metrics, { LCP: null, INP: null });
  assert.deepEqual(result.missing, ["LCP", "INP"]);
});

test("the latest final callback is retained without losing a legitimate zero measurement", () => {
  const result = summarizeMetrics([
    { document_id: "d1", name: "LCP", id: "l1", value: 90, final: true },
    { document_id: "d1", name: "LCP", id: "l1", value: 125, final: true },
    { document_id: "d1", name: "INP", id: "i1", value: 0, final: true },
  ], { documentId: "d1", hiddenObserved: true, inputVerified: true });
  assert.deepEqual(result, { complete: true, metrics: { LCP: { id: "l1", value: 125 }, INP: { id: "i1", value: 0 } }, missing: [] });
});

test("final values cannot establish completeness without a verified hidden flush and trusted input", () => {
  const events = [
    { document_id: "d", name: "LCP", id: "l", value: 12, final: true },
    { document_id: "d", name: "INP", id: "i", value: 16, final: true },
  ];
  assert.equal(summarizeMetrics(events, { documentId: "d", hiddenObserved: false, inputVerified: true }).complete, false);
  assert.equal(summarizeMetrics(events, { documentId: "d", hiddenObserved: true, inputVerified: false }).complete, false);
});

test("invalid metric numbers remain missing instead of improving the reported distribution", () => {
  for (const invalid of [null, NaN, Infinity, -1, "2"]) {
    const result = summarizeMetrics([
      { document_id: "d", name: "LCP", id: "l", value: invalid, final: true },
      { document_id: "d", name: "INP", id: "i", value: 17, final: true },
    ], { documentId: "d", hiddenObserved: true, inputVerified: true });
    assert.equal(result.complete, false);
    assert.equal(result.metrics.LCP, null);
    assert.deepEqual(result.missing, ["LCP"]);
  }
});

test("retained nested records redact cookie headers, credentials, and secret values embedded in errors", () => {
  const original = {
    status: 401, request: { headers: { Cookie: "fiestaboard_session=cookie-secret", Accept: "application/json" } },
    response: { headers: { "Set-Cookie": ["fiestaboard_session=cookie-secret; HttpOnly"], "Content-Type": "application/json" } },
    credentials: { username: "perf_alpha3", password: "password-secret" },
    error: "login rejected password-secret; session cookie-secret", counts: [4, 96],
  };
  const result = redact(original, ["password-secret", "cookie-secret"]);
  assert.deepEqual(result, {
    status: 401, request: { headers: { Cookie: "[REDACTED]", Accept: "application/json" } },
    response: { headers: { "Set-Cookie": "[REDACTED]", "Content-Type": "application/json" } },
    credentials: "[REDACTED]", error: "login rejected [REDACTED]; session [REDACTED]", counts: [4, 96],
  });
  assert.equal(original.credentials.password, "password-secret", "sanitization does not destroy the live in-memory credential");
});

test("collector bytes must match their declared digest before injection", () => {
  const metadata = { version: "5.1.0", attribution: true, format: "iife", sha256: "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", package_integrity: "sha512-fixture", license: "Apache-2.0" };
  assert.equal(verifyCollector(Buffer.from("abc"), metadata), true);
  assert.throws(() => verifyCollector(Buffer.from("abcd"), metadata), /hash|digest/i);
  assert.throws(() => verifyCollector(Buffer.from("abc"), { ...metadata, version: "latest" }), /version/i);
  assert.throws(() => verifyCollector(Buffer.from("abc"), { ...metadata, package_integrity: "" }), /integrity/i);
});

test("relay preserves compressed entity bytes and end-to-end response headers on a non-200 response", { timeout: 5000 }, async (t) => {
  const encoded = gzipSync(Buffer.from('{"error":"synthetic refusal"}'));
  const target = await upstream(t, (_req, res) => {
    res.writeHead(418, { "Content-Type": "application/json", "Content-Encoding": "gzip", "Content-Length": encoded.length,
      "Set-Cookie": ["one=first; Path=/; HttpOnly", "two=second; Path=/; SameSite=Lax"], "Cache-Control": "private, max-age=11", ETag: '"fixture"' });
    res.end(encoded);
  });
  const relay = await relayFor(t, target);
  const response = await request(`${relay.origin}/api/refusal`);
  assert.equal(response.status, 418);
  assert.deepEqual(response.body, encoded, "automatic fetch decompression would corrupt this entity");
  assert.equal(response.headers["content-encoding"], "gzip");
  assert.equal(response.headers["content-length"], String(encoded.length));
  assert.deepEqual(response.headers["set-cookie"], ["one=first; Path=/; HttpOnly", "two=second; Path=/; SameSite=Lax"]);
  assert.equal(response.headers["cache-control"], "private, max-age=11");
  assert.equal(response.headers.etag, '"fixture"');
});

test("relay forwards the actual request body, query, cookie and upstream Host without an API mock", { timeout: 5000 }, async (t) => {
  const payload = Buffer.from([0, 255, 123, 10, 13, 125]);
  let received;
  const target = await upstream(t, (req, res) => {
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      received = { body: Buffer.concat(chunks), method: req.method, url: req.url, cookie: req.headers.cookie, host: req.headers.host };
      res.writeHead(202, { "Content-Type": "application/octet-stream" });
      res.end(Buffer.from("upstream acknowledged"));
    });
  });
  const relay = await relayFor(t, target);
  const response = await request(`${relay.origin}/api/write?at=10%3A30%2B00%3A00`, {
    method: "POST", headers: { Cookie: "fiestaboard_session=synthetic", "Content-Type": "application/octet-stream", "Content-Length": payload.length }, body: payload,
  });
  assert.deepEqual(received, { body: payload, method: "POST", url: "/api/write?at=10%3A30%2B00%3A00", cookie: "fiestaboard_session=synthetic", host: new URL(target).host });
  assert.equal(response.status, 202);
  assert.equal(response.body.toString(), "upstream acknowledged");
});

test("relay does not turn cacheable upstream responses into its own cached API answers", { timeout: 5000 }, async (t) => {
  let calls = 0;
  const target = await upstream(t, (_req, res) => {
    calls += 1;
    res.writeHead(200, { "Cache-Control": "public, max-age=3600" });
    res.end(String(calls));
  });
  const relay = await relayFor(t, target);
  assert.equal((await request(`${relay.origin}/api/current`)).body.toString(), "1");
  assert.equal((await request(`${relay.origin}/api/current`)).body.toString(), "2");
});

test("redirect translation retains same-origin paths while identifying foreign destinations", () => {
  const origins = { upstreamOrigin: "http://hub:3000", relayOrigin: "http://127.0.0.1:1234" };
  assert.deepEqual(relayLocation("/login?next=%2Fpages", origins), { location: "/login?next=%2Fpages", allowed: true });
  assert.deepEqual(relayLocation("http://hub:3000/pages?q=1#item", origins), { location: "http://127.0.0.1:1234/pages?q=1#item", allowed: true });
  assert.deepEqual(relayLocation("https://foreign.invalid/auth", origins), { location: "https://foreign.invalid/auth", allowed: false });
  assert.deepEqual(relayLocation("//foreign.invalid/auth", origins), { location: "//foreign.invalid/auth", allowed: false });
  assert.deepEqual(relayLocation("http://hub:3001/pages", origins), { location: "http://hub:3001/pages", allowed: false });
});

test("relay returns an upstream redirect without following it or changing its status", { timeout: 5000 }, async (t) => {
  let calls = 0;
  const target = await upstream(t, (_req, res) => {
    calls += 1;
    res.writeHead(307, { Location: "/destination?original=1" });
    res.end("redirect entity");
  });
  const relay = await relayFor(t, target);
  const response = await request(`${relay.origin}/api/redirect`);
  assert.equal(response.status, 307);
  assert.equal(response.headers.location, "/destination?original=1");
  assert.equal(response.body.toString(), "redirect entity");
  assert.equal(calls, 1);
});

test("runner fails closed on missing public manifest before any browser or login work", async () => {
  await assert.rejects(runBrowserBatch({}), /manifest/i);
});

test("relay translates only its exact Origin and Referer authority to the declared nginx origin", () => {
  const headers = { host: "127.0.0.1:1234", origin: "http://127.0.0.1:1234", referer: "http://127.0.0.1:1234/pages?q=1", cookie: "fiestaboard_session=synthetic" };
  assert.deepEqual(relayRequestHeaders(headers, { relayOrigin: "http://127.0.0.1:1234", upstreamOrigin: "http://hub:3000" }), {
    host: "hub:3000", origin: "http://hub:3000", referer: "http://hub:3000/pages?q=1", cookie: "fiestaboard_session=synthetic",
  });
  assert.equal(headers.origin, "http://127.0.0.1:1234", "upstream translation leaves the original browser observation intact");
});

test("a foreign or merely similar browser origin cannot gain the target's same-origin privileges", () => {
  const origins = { relayOrigin: "http://127.0.0.1:1234", upstreamOrigin: "http://hub:3000" };
  assert.deepEqual(relayRequestHeaders({ host: "local", origin: "http://127.0.0.1:12345", referer: "http://127.0.0.1:1234.evil.invalid/pages" }, origins), {
    host: "hub:3000", origin: "http://127.0.0.1:12345", referer: "http://127.0.0.1:1234.evil.invalid/pages",
  });
  assert.deepEqual(relayRequestHeaders({ origin: "null", referer: "malformed", connection: "keep-alive, X-Local-Hop", "x-local-hop": "discard", accept: "application/json" }, origins), {
    host: "hub:3000", origin: "null", referer: "malformed", accept: "application/json",
  });
});

test("the running relay applies exact-origin translation on real forwarded requests", { timeout: 5000 }, async (t) => {
  let received;
  const target = await upstream(t, (req, res) => {
    received = { origin: req.headers.origin, referer: req.headers.referer };
    res.end("accepted");
  });
  const relay = await relayFor(t, target);
  await request(`${relay.origin}/api/read`, { headers: { Origin: relay.origin, Referer: `${relay.origin}/schedule?board=perf-f` } });
  assert.deepEqual(received, { origin: target, referer: `${target}/schedule?board=perf-f` });
});

// Public summary fields from alpha.3 SessionRecord.summary() and session route.
// No session-cookie value exists in this fixture.
const session = {
  id: "synthetic-session", kind: "browser", device_name: "Mozilla/5.0 synthetic",
  client_id: "", app_version: "", method: "password",
  created_at: "2026-11-17T10:00:00+00:00", expires_at: "2026-11-18T10:00:00+00:00", last_active_at: "2026-11-17T11:00:00+00:00",
  last_shown_at: null, shown_panels: [], approved_by: null,
};
const batchTiming = { nowUtc: "2026-11-17T11:00:00Z", clock: () => "2026-11-17T11:00:00Z", batchSeconds: 3600, marginSeconds: 300, expectedCount: 1 };

test("session preflight retains only safe count and actual expiry metadata for a sufficiently long real browser session", () => {
  assert.deepEqual(validateSessionBatch({ sessions: [session], current_session_id: session.id }, batchTiming), {
    session_count: 1, current_expires_at: "2026-11-18T10:00:00+00:00", kind: "browser",
  });
});

test("session expiry must strictly exceed the whole batch and explicit margin instead of assuming a seven-day lifetime", () => {
  for (const expires_at of ["2026-11-17T12:05:00Z", "2026-11-17T11:30:00Z", "not-a-date", "2026-11-18T10:00:00"]) {
    assert.throws(() => validateSessionBatch({ sessions: [{ ...session, expires_at }], current_session_id: session.id }, batchTiming), /expiry|expires/i);
  }
});

test("missing current session, token kind, or session-count drift aborts the batch before sampling", () => {
  assert.throws(() => validateSessionBatch({ sessions: [session], current_session_id: "absent" }, batchTiming), /current session/i);
  assert.throws(() => validateSessionBatch({ sessions: [{ ...session, kind: "native" }], current_session_id: session.id }, batchTiming), /browser/i);
  assert.throws(() => validateSessionBatch({ sessions: [session, { ...session, id: "unexpected-extra-login" }], current_session_id: session.id }, batchTiming), /count|growth/i);
});

test("host-only session cookies can be reused in memory while explicit Domain cookies fail without rewriting", () => {
  assert.deepEqual(validateSessionCookieHeaders(["fiestaboard_session=synthetic-private; HttpOnly; Path=/; SameSite=lax"]), {
    hostOnly: true, httpOnly: true, sameSite: "lax", secure: false,
  });
  assert.throws(() => validateSessionCookieHeaders(["fiestaboard_session=synthetic-private; Domain=hub; HttpOnly; Path=/; SameSite=lax"]), /domain/i);
  assert.throws(() => validateSessionCookieHeaders(["another_cookie=value; Path=/"]), /session cookie/i);
  assert.throws(() => validateSessionCookieHeaders(["fiestaboard_session=synthetic-private; Path=/"]), /httponly|samesite/i);
});

// Boundary harness for our initialization/serialization/lifecycle code, not a
// browser simulation or proof of web-vitals correctness. Real visibility,
// trusted events and callback drain still require root's Chromium trace.
function collectorRealm({ wrappedSource, theme = "light", observerTypes = [], idleTimedOut = false } = {}) {
  const events = [];
  const listeners = new Map();
  const registrations = {};
  const local = new Map();
  const session = new Map();
  const observerCallbacks = new Map();
  const scheduling = { frames: 0, idle: 0 };
  const realm = {
    location: { protocol: "http:", href: "http://127.0.0.1:1234/pages" },
    document: { visibilityState: "visible" }, isSecureContext: true,
    crypto: { randomUUID: () => "document-one" },
    performance: { now: () => 25, timeOrigin: 1000 },
    localStorage: { setItem: (key, value) => local.set(key, value) },
    sessionStorage: { setItem: (key, value) => session.set(key, value) },
    addEventListener: (type, callback) => listeners.set(type, [...(listeners.get(type) ?? []), callback]),
    setTimeout, clearTimeout,
    requestAnimationFrame: (callback) => { scheduling.frames += 1; return setImmediate(() => callback(25)); },
    cancelAnimationFrame: clearImmediate,
    requestIdleCallback: (callback) => { scheduling.idle += 1; return setImmediate(() => callback({ didTimeout: idleTimedOut, timeRemaining: () => 20 })); },
    cancelIdleCallback: clearImmediate,
    PerformanceObserver: class {
      static supportedEntryTypes = observerTypes;
      constructor(callback) { this.callback = callback; }
      observe({ type }) { observerCallbacks.set(type, this.callback); }
      takeRecords() { return []; }
    },
    webVitals: {
      onLCP: (callback, options) => { registrations.LCP = { callback, options }; },
      onINP: (callback, options) => { registrations.INP = { callback, options }; },
    },
    __perfMetric: async (event) => { events.push(JSON.parse(JSON.stringify(event))); },
  };
  realm.window = realm;
  realm.top = realm;
  let source = `(${installBrowserCollector.toString()})(${JSON.stringify({ boardId: "perf-n", libraryFilter: "all", theme })})`;
  if (wrappedSource) {
    realm.__fixtureCollector = realm.webVitals;
    delete realm.webVitals;
    source = buildCollectorInitScript(wrappedSource, { boardId: "perf-n", libraryFilter: "all", theme });
    assert.equal(typeof source, "string", "the complete same-script collector wrapper exists");
    source = `(function(){\n${source}\n})()`;
  }
  const context = vm.createContext(realm);
  const installed = vm.runInContext(source, context);
  const api = installed ?? realm.__perfBrowser;
  assert.ok(api && typeof api.state === "function", "bootstrap returns the lifecycle controller");
  assert.ok(registrations.LCP && registrations.INP, "both official metric registrations exist");
  const fire = (type, properties) => { for (const listener of listeners.get(type) ?? []) listener(properties); };
  const deliver = (type, entries) => { const callback = observerCallbacks.get(type); assert.ok(callback, `observer exists for ${type}`); callback({ getEntries: () => entries }); };
  return { api, realm, events, registrations, fire, local, session, deliver, scheduling };
}

test("bootstrap configures official final-only callbacks and initializes independent browser preferences", async () => {
  const c = collectorRealm();
  assert.equal(c.registrations.LCP.options.reportAllChanges, false);
  assert.equal(c.registrations.INP.options.reportAllChanges, false);
  assert.equal(c.registrations.INP.options.durationThreshold, 16);
  assert.equal(c.local.get("fiestaboard_current_board"), "perf-n");
  assert.equal(c.local.get("fiestaboard_pages_view_mode"), "grid");
  assert.equal(c.session.get("fiestaboard_pages_display_filter"), "all");
  await c.api.drain();
  const ready = c.events.find((event) => event.event === "collector_ready");
  assert.equal(ready.document_id, "document-one");
  assert.equal(ready.event_timing_supported, false, "unsupported is recorded rather than invented zero");
});

test("an untrusted DOM event cannot finalize LCP, while a genuine first input can preserve a real zero", async () => {
  const c = collectorRealm();
  c.fire("click", { isTrusted: false });
  c.registrations.LCP.callback({ name: "LCP", id: "l1", value: 40, delta: 40, entries: [] });
  c.fire("keydown", { isTrusted: true });
  c.registrations.LCP.callback({ name: "LCP", id: "l1", value: 0, delta: -40, entries: [] });
  await c.api.drain();
  const metrics = c.events.filter((event) => event.record_type === "browser_metric");
  assert.equal(metrics[0].final, false);
  assert.equal(metrics[1].final, true);
  assert.equal(metrics[1].value, 0);
  assert.equal(c.api.state().trustedInputCount, 1);
});

test("controlled hidden flush retains a received final INP callback without synthesizing a missing callback", async () => {
  const c = collectorRealm();
  c.fire("click", { isTrusted: true });
  c.api.beforeHide();
  c.realm.document.visibilityState = "hidden";
  c.fire("visibilitychange", { isTrusted: true });
  await c.api.drain();
  assert.equal(c.events.some((event) => event.name === "INP"), false, "hidden alone cannot manufacture a metric");
  c.registrations.INP.callback({ name: "INP", id: "i1", value: 24, delta: 24, entries: [] });
  await c.api.drain();
  const metric = c.events.find((event) => event.name === "INP");
  assert.equal(metric.final, true);
  assert.equal(metric.document_id, "document-one");
  assert.equal(c.api.state().hiddenObserved, true);
  assert.equal(c.api.state().invalidReason, null);
});

test("an earlier hide or BFCache restore invalidates the first-foreground document lifecycle", () => {
  const hidden = collectorRealm();
  hidden.realm.document.visibilityState = "hidden";
  hidden.fire("visibilitychange", { isTrusted: true });
  hidden.api.beforeHide();
  assert.equal(hidden.api.state().invalidReason, "unexpected_hidden");
  const restored = collectorRealm();
  restored.fire("pageshow", { persisted: true, isTrusted: true });
  assert.equal(restored.api.state().invalidReason, "bfcache_restore");
});

test("collector serialization allowlists scalar attribution and raw entry fields instead of retaining DOM or credential objects", async () => {
  const c = collectorRealm();
  c.fire("click", { isTrusted: true });
  c.registrations.LCP.callback({
    name: "LCP", id: "l1", value: 310, delta: 310, rating: "good", password: "never-retain", navigationType: "navigate",
    entries: [{ entryType: "largest-contentful-paint", startTime: 310, size: 1200, renderTime: 310, loadTime: 0, url: "", element: { textContent: "private" } }],
    attribution: { timeToFirstByte: 10, elementRenderDelay: 300, target: "main h1", secret: "never-retain", lcpEntry: { element: { textContent: "private" } } },
  });
  await c.api.drain();
  const metric = c.events.find((event) => event.record_type === "browser_metric");
  assert.equal(metric.attribution.timeToFirstByte, 10);
  assert.equal(metric.attribution.elementRenderDelay, 300);
  assert.equal(metric.attribution.target, "main h1");
  assert.deepEqual(metric.entries, [{ entryType: "largest-contentful-paint", startTime: 310, size: 1200, renderTime: 310, loadTime: 0, url: "" }]);
  assert.equal(JSON.stringify(metric).includes("private"), false);
  assert.equal(JSON.stringify(metric).includes("never-retain"), false);
});

test("the same init script exposes a lexically scoped official-IIFE var to bootstrap under Playwright's function wrapper", async () => {
  const c = collectorRealm({ wrappedSource: "var webVitals = __fixtureCollector;" });
  c.fire("click", { isTrusted: true });
  c.registrations.LCP.callback({ name: "LCP", id: "wrapped-lcp", value: 45, delta: 45, entries: [] });
  await c.api.drain();
  assert.equal(c.events.find((event) => event.name === "LCP").value, 45);
});

const publishedSource = "83236253aa8103db856b7efa456e088b9c9ec548";
const armManifest = "sha256:e0127d1f0eed00e13cd394f098580c2b96579b458731b6dc5d7ee842c7645886";
const armImage = "sha256:ddf771f44a75dde50288922b9d38c75b88aad0c4449ccef2a5d896c790825cae";

function evidenceFixture() {
  const manifest = { schema_version: 1, seed_id: "seed-one", source_commit: publishedSource, base_url: "http://hub:3000", manifest_sha256: "separate-canonical-content-identity" };
  const ownership = { source_commit: publishedSource, image_manifest: armManifest, container_id: "owned-container", base_url: "http://hub:3000", seed_id: "seed-one", data_dir: "/synthetic/seed-one", empty_before_start: true, prestart_entries: [], attested_utc: "2026-11-17T10:00:00Z" };
  const manifestBytes = Buffer.from(`${JSON.stringify(manifest)}\n`);
  const ownershipBytes = Buffer.from(`${JSON.stringify(ownership)}\n`);
  return {
    manifestBytes, ownershipBytes, nowUtc: "2026-11-17T11:00:00Z", maxAgeSeconds: 300, diagnostic: true, targetOrigin: "http://hub:3000",
    context: {
      schema_version: 1, run_id: "run-one", seed_id: "seed-one", source_commit: publishedSource, data_dir: "/synthetic/seed-one", captured_utc: "2026-11-17T10:59:30Z",
      manifest_sha256: createHash("sha256").update(manifestBytes).digest("hex"), ownership_sha256: createHash("sha256").update(ownershipBytes).digest("hex"), target_origin: "http://hub:3000",
      container: { id: "owned-container", image_id: armImage, manifest_digest: armManifest, architecture: "arm64" },
      exclusion: { task_id: "prodPerf", running_ids: ["prodPerf"], container_names: ["hub", "web", "api"], checked_utc: "2026-11-17T10:59:30Z", browser_lease_owner: "prodPerf" },
      host: { os: "Linux", architecture: "arm64", cpu: null, memory: null, unavailable: ["cpu", "memory"] },
      calibration: { relay_report_path: null, lifecycle_report_path: null },
    },
  };
}

test("a diagnostic accepts freshly bound original file bytes without confusing the manifest's internal canonical hash", () => {
  const result = validateRunEvidence(evidenceFixture());
  assert.ok(result, "bound evidence is returned");
  assert.equal(result.manifest.seed_id, "seed-one");
  assert.equal(result.context.container.architecture, "arm64");
  assert.equal(result.diagnostic, true);
});

test("changing manifest whitespace or ownership content breaks the actual-file-byte binding before setup", () => {
  const manifestChanged = evidenceFixture();
  manifestChanged.manifestBytes = Buffer.concat([manifestChanged.manifestBytes, Buffer.from(" ")]);
  assert.throws(() => validateRunEvidence(manifestChanged), /manifest.*hash/i);
  const ownershipChanged = evidenceFixture();
  ownershipChanged.ownershipBytes = Buffer.concat([ownershipChanged.ownershipBytes, Buffer.from(" ")]);
  assert.throws(() => validateRunEvidence(ownershipChanged), /ownership.*hash/i);
});

test("an unrelated seed, container, source revision or measured origin cannot borrow a valid context", () => {
  for (const [key, value] of [["seed_id", "other-seed"], ["source_commit", "candidate-source"], ["target_origin", "http://other:3000"], ["data_dir", "/owner/data"]]) {
    const input = evidenceFixture();
    input.context[key] = value;
    assert.throws(() => validateRunEvidence(input), /bind|source|origin|seed|data/i);
  }
  const containerChanged = evidenceFixture();
  containerChanged.context.container.id = "another-container";
  assert.throws(() => validateRunEvidence(containerChanged), /container/i);
  const architectureChanged = evidenceFixture();
  architectureChanged.context.container.architecture = "amd64";
  assert.throws(() => validateRunEvidence(architectureChanged), /image|manifest|architecture/i);
});

test("stale or future inventory observations cannot establish current exclusion", () => {
  for (const captured_utc of ["2026-11-17T10:54:59Z", "2026-11-17T11:00:01Z"]) {
    const input = evidenceFixture();
    input.context.captured_utc = captured_utc;
    assert.throws(() => validateRunEvidence(input), /fresh|stale|future|time/i);
  }
  const staleInventory = evidenceFixture();
  staleInventory.context.exclusion.checked_utc = "2026-11-17T10:00:00Z";
  assert.throws(() => validateRunEvidence(staleInventory), /fresh|stale|time/i);
});

test("a nonempty prestart store cannot be relabeled isolated by rehashing its ownership evidence", () => {
  const input = evidenceFixture();
  const owner = JSON.parse(input.ownershipBytes.toString());
  owner.prestart_entries = ["users.json"];
  input.ownershipBytes = Buffer.from(JSON.stringify(owner));
  input.context.ownership_sha256 = createHash("sha256").update(input.ownershipBytes).digest("hex");
  assert.throws(() => validateRunEvidence(input), /empty|store/i);
});

test("baseline mode fails closed when diagnostic-only relay and lifecycle calibration is absent", () => {
  const input = evidenceFixture();
  input.diagnostic = false;
  assert.throws(() => validateRunEvidence(input), /calibrat/i);
});

function authUpstream(t, { expire = "2026-11-18T10:00:00+00:00", protectedStatus = 200, setupRequired = false, holdProtected = false } = {}) {
  const observed = { logins: 0, loginPayload: null, cookies: [], records: [] };
  let markStarted;
  let markClosed;
  observed.protectedStarted = new Promise((resolve) => { markStarted = resolve; });
  observed.protectedClosed = new Promise((resolve) => { markClosed = resolve; });
  return upstream(t, (req, res) => {
    observed.cookies.push({ path: req.url, value: req.headers.cookie });
    const chunks = [];
    req.on("data", (chunk) => chunks.push(chunk));
    req.on("end", () => {
      res.setHeader("Content-Type", "application/json");
      if (req.url === "/api/auth/status") {
        res.end(JSON.stringify({ enabled: true, setup_required: setupRequired, authenticated: Boolean(req.headers.cookie), auth_kind: req.headers.cookie ? "browser" : null }));
      } else if (req.url === "/api/auth/login") {
        observed.logins += 1;
        observed.loginPayload = JSON.parse(Buffer.concat(chunks).toString());
        res.setHeader("Set-Cookie", "fiestaboard_session=cookie-secret; HttpOnly; Path=/; SameSite=lax");
        res.end(JSON.stringify({ status: "ok", username: "perf_alpha3" }));
      } else if (req.url === "/api/auth/sessions") {
        res.end(JSON.stringify({ sessions: [{ ...session, expires_at: expire }], current_session_id: session.id }));
      } else {
        if (holdProtected) {
          res.once("close", markClosed);
          markStarted();
          return;
        }
        res.statusCode = protectedStatus;
        res.end(JSON.stringify(protectedStatus === 401 ? { detail: "cookie-secret password-secret" } : { pages: [], total: 0 }));
      }
    });
  }).then((origin) => ({ origin, observed }));
}

test("one genuine login supplies reusable in-memory cookies and authenticated internal/v1 reads without repeated login", { timeout: 5000 }, async (t) => {
  const { origin, observed } = await authUpstream(t);
  const batch = await createBatchSession({ origin, credentials: { username: "perf_alpha3", password: "password-secret" }, userAgent: "Mozilla/5.0 test-browser", ...batchTiming, timeoutMs: 1000, onRecord: (record) => observed.records.push(record) });
  assert.ok(batch && typeof batch.getJson === "function", "real batch session client is returned");
  const first = batch.cookiesForContext();
  const second = batch.cookiesForContext();
  assert.equal(first[0].value, "cookie-secret");
  assert.notEqual(first, second, "each context receives an independent in-memory cookie array");
  await batch.getJson("/api/pages");
  await batch.getJson("/api/v1/pages");
  await batch.verifySession();
  assert.equal(observed.logins, 1);
  assert.deepEqual(observed.loginPayload, { username: "perf_alpha3", password: "password-secret", remember_me: false });
  assert.ok(observed.cookies.filter((record) => ["/api/pages", "/api/v1/pages"].includes(record.path)).every((record) => record.value === "fiestaboard_session=cookie-secret"));
  assert.equal(JSON.stringify(batch).includes("cookie-secret"), false);
  assert.equal(JSON.stringify(observed.records).includes("password-secret"), false);
});

test("a protected401 aborts the batch and preserves sanitized failure evidence without relogin or retry", { timeout: 5000 }, async (t) => {
  const { origin, observed } = await authUpstream(t, { protectedStatus: 401 });
  const batch = await createBatchSession({ origin, credentials: { username: "perf_alpha3", password: "password-secret" }, userAgent: "Mozilla/5.0 test-browser", ...batchTiming, timeoutMs: 1000, onRecord: (record) => observed.records.push(record) });
  assert.ok(batch && typeof batch.getJson === "function");
  await assert.rejects(batch.getJson("/api/pages"), /401|authentication/i);
  await assert.rejects(batch.getJson("/api/pages"), /abort/i);
  assert.equal(observed.logins, 1);
  assert.equal(observed.cookies.filter((record) => record.path === "/api/pages").length, 1);
  assert.ok(observed.records.some((record) => record.status === 401));
  assert.equal(JSON.stringify(observed.records).includes("cookie-secret"), false);
  assert.equal(JSON.stringify(observed.records).includes("password-secret"), false);
});

test("an unprovisioned store is rejected before the batch can log in or create anything", { timeout: 5000 }, async (t) => {
  const { origin, observed } = await authUpstream(t, { setupRequired: true });
  await assert.rejects(createBatchSession({ origin, credentials: { username: "perf_alpha3", password: "password-secret" }, userAgent: "Mozilla/5.0 test-browser", ...batchTiming, timeoutMs: 1000 }), /provision|setup|store/i);
  assert.equal(observed.logins, 0);
});

test("the default CLI cannot silently exit successfully without an explicit configuration", () => {
  const result = spawnSync(process.execPath, [new URL("./web_run.mjs", import.meta.url).pathname], { encoding: "utf8", timeout: 5000 });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /config|usage/i);
});

function officialProvenance() {
  return {
    name: "web-vitals", version: "5.1.0", license: "Apache-2.0", verified_integrity: true,
    registry_metadata_url: "https://registry.npmjs.org/web-vitals/5.1.0",
    tarball_url: "https://registry.npmjs.org/web-vitals/-/web-vitals-5.1.0.tgz",
    npm_integrity: "sha512-ArI3kx5jI0atlTtmV0fWU3fjpLmq/nD3Zr1iFFlJLaqa5wLBkUSzINwBPySCX/8jRyjlmy1Volw1kz1g9XE4Jg==",
    tarball_sha256: "5a508f690262ddacd4937f7fcb2f15f020fa94c47aad0d47af1f716296144d61",
    members: { "package/dist/web-vitals.attribution.iife.js": { bytes: 11582, sha256: "397a8cffdeec35be161d00e3ed1378a644223f710dafee49584d376a64d3b9a0" } },
    official_source: "https://github.com/GoogleChrome/web-vitals/tree/v5.1.0", runtime_executed: false,
  };
}

test("the runner derives collector byte verification from the exact root-verified official package provenance", () => {
  assert.deepEqual(collectorMetadataFromProvenance(officialProvenance()), {
    version: "5.1.0", attribution: true, format: "iife", license: "Apache-2.0",
    package_integrity: "sha512-ArI3kx5jI0atlTtmV0fWU3fjpLmq/nD3Zr1iFFlJLaqa5wLBkUSzINwBPySCX/8jRyjlmy1Volw1kz1g9XE4Jg==",
    sha256: "397a8cffdeec35be161d00e3ed1378a644223f710dafee49584d376a64d3b9a0",
  });
});

test("an unverified package, mutable version or changed packaged collector cannot reuse the pinned provenance", () => {
  for (const patch of [{ verified_integrity: false }, { version: "latest" }, { tarball_sha256: "other-tarball" }]) {
    assert.throws(() => collectorMetadataFromProvenance({ ...officialProvenance(), ...patch }), /integrity|version|tarball|pin/i);
  }
  const changed = officialProvenance();
  changed.members["package/dist/web-vitals.attribution.iife.js"].sha256 = "candidate-build";
  assert.throws(() => collectorMetadataFromProvenance(changed), /digest|pin/i);
});

const browserPreferences = { theme: "light", locale: "en-US", next_locale: "en", timezone: "UTC", display: { reduce_motion: false, board_animations: "on", site_animations: "on", board_flap_speed: "standard" } };
const routeManifest = {
  browser_preferences: browserPreferences,
  boards: {
    flagship: { id: "perf-f", name: "PERF Flagship", device_type: "flagship", rows: 6, cols: 22, page_ids: ["seed/page-one"] },
    note: { id: "perf-n", name: "PERF Note", device_type: "note", rows: 3, cols: 15, page_ids: ["note-one"] },
  },
  pages: [
    { id: "seed/page-one", name: "PERF F 01", geometry: "flagship", kind: "literal", template: ["PERF F 01", "FIXED", "END", "", "", ""] },
    { id: "note-one", name: "PERF N 01", geometry: "note", kind: "literal", template: ["PERF N 01", "FIXED", "END"] },
  ],
};
const routeConfig = { profile: "desktop", geometry: "flagship", route: "home", cache: "cold-browser", batch: 1, samples: 1, diagnostic: true, warmups: 0 };

test("editor planning uses the selected geometry's actual literal ID and independent board/filter preferences", () => {
  const plan = planBrowserBatch({ ...routeConfig, route: "editor" }, routeManifest);
  assert.ok(plan, "one explicit route batch is returned");
  assert.equal(plan.path, "/pages/edit/seed%2Fpage-one");
  assert.equal(plan.page.id, "seed/page-one");
  assert.deepEqual(plan.preferences, { boardId: "perf-f", libraryFilter: "all" });
  assert.equal(plan.diagnostic, true);
});

test("All pages and compatible-board library cases retain distinct declared96/24 counts and cache labels", () => {
  const all = planBrowserBatch({ ...routeConfig, route: "pages" }, routeManifest);
  const compatible = planBrowserBatch({ ...routeConfig, profile: "phone", geometry: "note", route: "pages", library_filter: "selected-board", cache: "warm-pwa" }, routeManifest);
  assert.ok(all && compatible);
  assert.equal(all.expectedLibraryCount, 96);
  assert.equal(compatible.expectedLibraryCount, 24);
  assert.equal(compatible.preferences.boardId, "perf-n");
  assert.equal(compatible.preferences.libraryFilter, "perf-n");
  assert.equal(all.cache, "cold-browser");
  assert.equal(compatible.cache, "warm-pwa");
});

test("invalid route/geometry/cache, missing literal and undersized baseline batches fail rather than selecting a fallback", () => {
  for (const change of [{ route: "unknown" }, { geometry: "other" }, { cache: "warm-ish" }, { samples: 0 }, { diagnostic: false, samples: 19 }]) {
    assert.throws(() => planBrowserBatch({ ...routeConfig, ...change }, routeManifest), /route|geometry|cache|sample|baseline/i);
  }
  assert.throws(() => planBrowserBatch(routeConfig, { ...routeManifest, pages: [] }), /literal|page/i);
});

async function temporaryDirectory(t) {
  const directory = await mkdtemp(path.join(os.tmpdir(), "perf-web-test-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  return directory;
}

test("private credentials are read only from a mode0600 regular file and never from a symlink or public-readable file", async (t) => {
  const directory = await temporaryDirectory(t);
  const file = path.join(directory, "credentials.json");
  await writeFile(file, JSON.stringify({ username: "perf_alpha3", password: "password-secret" }), { mode: 0o600 });
  assert.deepEqual(await readPrivateCredentials(file), { username: "perf_alpha3", password: "password-secret" });
  await chmod(file, 0o644);
  await assert.rejects(readPrivateCredentials(file), /0600|private|permission/i);
  await chmod(file, 0o600);
  const link = path.join(directory, "linked.json");
  await symlink(file, link);
  await assert.rejects(readPrivateCredentials(link), /regular|symlink/i);
});

test("invalid credential/config JSON never echoes secret-containing input into retained exceptions", async (t) => {
  const directory = await temporaryDirectory(t);
  const file = path.join(directory, "invalid.json");
  await writeFile(file, '{"password":"password-secret"', { mode: 0o600 });
  for (const read of [readPrivateCredentials, loadRunConfig]) {
    await assert.rejects(read(file), (error) => !String(error).includes("password-secret") && /json|config|credential/i.test(String(error)));
  }
});

test("explicit CLI config is parsed before the missing-manifest gate and is not printed into stderr", async (t) => {
  const directory = await temporaryDirectory(t);
  const file = path.join(directory, "run.json");
  await writeFile(file, JSON.stringify({ diagnostic: true, synthetic_private_marker: "password-secret" }));
  const config = await loadRunConfig(file);
  assert.ok(config, "explicit config was read");
  assert.equal(config.diagnostic, true);
  const result = spawnSync(process.execPath, [new URL("./web_run.mjs", import.meta.url).pathname, "--config", file], { encoding: "utf8", timeout: 5000 });
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /manifest/i);
  assert.equal(result.stderr.includes("password-secret"), false);
});

async function verifierHarness(t, body) {
  const directory = await temporaryDirectory(t);
  await writeFile(path.join(directory, "runtime_common.py"), `
class HttpResult:
    def __init__(self, status, body, **kwargs):
        self.status, self.body = status, body
class JsonClient:
    def __init__(self, base_url, credentials, *, transport):
        if credentials:
            raise ValueError("credentials must never enter child")
        self.base_url, self.transport = base_url, transport
    def request(self, method, path, payload=None):
        return self.transport(method, self.base_url + path, payload, {}, 1)
`);
  await writeFile(path.join(directory, "runtime_seed.py"), `def verify_manifest(client, manifest):\n${body.split("\n").map((line) => `    ${line}`).join("\n")}\n`);
  return directory;
}

const verificationFlags = { exact_counts: true, exact_ids: true, geometry: true, read_back: true, runtime_manual_state: true, browser_preferences: true };

test("the real Python bridge reuses the Node cookie session for serial public GET verification without another login", { timeout: 5000 }, async (t) => {
  const { origin, observed } = await authUpstream(t);
  const batch = await createBatchSession({ origin, credentials: { username: "perf_alpha3", password: "password-secret" }, userAgent: "Mozilla/5.0 test-browser", ...batchTiming, timeoutMs: 1000 });
  const harness = await verifierHarness(t, 'answer = client.request("GET", "/api/v1/pages")\nif answer.status != 200 or answer.body != {"pages": [], "total": 0}:\n    raise ValueError("read failed")\nreturn {"exact_counts": True, "exact_ids": True, "geometry": True, "read_back": True, "runtime_manual_state": True, "browser_preferences": True}');
  const result = await verifyFixtureThroughSession({ manifest: { seed_id: "seed-one" }, origin, session: batch, apiHarnessDir: harness, timeoutMs: 2000, maxRequests: 10 });
  assert.deepEqual(result, verificationFlags);
  assert.equal(observed.logins, 1);
  assert.equal(observed.cookies.find((record) => record.path === "/api/v1/pages").value, "fiestaboard_session=cookie-secret");
});

test("a verification child cannot mutate the fixture through the read-only bridge", { timeout: 5000 }, async (t) => {
  const harness = await verifierHarness(t, 'client.request("PUT", "/api/settings/board", {"boards": []})\nreturn {"exact_counts": True}');
  let requests = 0;
  await assert.rejects(verifyFixtureThroughSession({ manifest: {}, origin: "http://hub:3000", session: { getJson: async () => { requests += 1; return {}; } }, apiHarnessDir: harness, timeoutMs: 2000, maxRequests: 10 }), /GET|read.only|verifier/i);
  assert.equal(requests, 0);
});

test("an exited child or missing verification flags cannot become a successful fixture preflight", { timeout: 5000 }, async (t) => {
  for (const source of ['raise ValueError("verification failed")', 'client.request("GET", "/api/read")\nreturn {"exact_counts": True}']) {
    const harness = await verifierHarness(t, source);
    await assert.rejects(verifyFixtureThroughSession({ manifest: {}, origin: "http://hub:3000", session: { getJson: async () => ({}) }, apiHarnessDir: harness, timeoutMs: 2000, maxRequests: 10 }), /verif|child|complete/i);
  }
});

test("verification requests are capped before an unexpected extra request reaches the session", { timeout: 5000 }, async (t) => {
  const harness = await verifierHarness(t, 'client.request("GET", "/api/first")\nclient.request("GET", "/api/second")\nreturn {"exact_counts": True, "exact_ids": True, "geometry": True, "read_back": True, "runtime_manual_state": True}');
  let requests = 0;
  await assert.rejects(verifyFixtureThroughSession({ manifest: {}, origin: "http://hub:3000", session: { getJson: async () => { requests += 1; return {}; } }, apiHarnessDir: harness, timeoutMs: 2000, maxRequests: 1 }), /limit|many/i);
  assert.equal(requests, 1);
});

test("an overall verifier deadline aborts an in-flight read and terminates the child instead of hanging before timing", { timeout: 5000 }, async (t) => {
  const harness = await verifierHarness(t, 'client.request("GET", "/api/never-finishes")\nreturn {}');
  let sawAbort = false;
  await assert.rejects(verifyFixtureThroughSession({ manifest: {}, origin: "http://hub:3000", session: { getJson: async (_path, { signal }) => new Promise((_resolve, reject) => signal.addEventListener("abort", () => { sawAbort = true; reject(new Error("aborted read")); }, { once: true })) }, apiHarnessDir: harness, timeoutMs: 250, maxRequests: 1 }), /deadline|timeout/i);
  assert.equal(sawAbort, true);
});

test("oversized verifier responses fail closed instead of growing an unbounded IPC frame", { timeout: 5000 }, async (t) => {
  const harness = await verifierHarness(t, 'client.request("GET", "/api/oversized")\nreturn {}');
  await assert.rejects(verifyFixtureThroughSession({ manifest: {}, origin: "http://hub:3000", session: { getJson: async () => ({ content: "x".repeat(2000) }) }, apiHarnessDir: harness, timeoutMs: 2000, maxRequests: 1, maxFrameBytes: 1000 }), /large|size|limit/i);
});

test("batch API cancellation closes a real in-flight request rather than leaving preflight traffic alive", { timeout: 5000 }, async (t) => {
  const { origin, observed } = await authUpstream(t, { holdProtected: true });
  const batch = await createBatchSession({ origin, credentials: { username: "perf_alpha3", password: "password-secret" }, userAgent: "Mozilla/5.0 test-browser", ...batchTiming, timeoutMs: 1000 });
  const controller = new AbortController();
  const pending = batch.getJson("/api/pages", { signal: controller.signal });
  await observed.protectedStarted;
  controller.abort();
  await assert.rejects(pending, /abort/i);
  await observed.protectedClosed;
});

test("exclusion rejects a competing PROD task and missing or empty owned task/lease identity", () => {
  const concurrent = evidenceFixture();
  concurrent.context.exclusion.running_ids.push("prodOther");
  assert.throws(() => validateRunEvidence(concurrent), /exclusion|owner|active|serial/i);
  const emptyOwner = evidenceFixture();
  emptyOwner.context.exclusion.running_ids = [""];
  emptyOwner.context.exclusion.browser_lease_owner = "";
  assert.throws(() => validateRunEvidence(emptyOwner), /exclusion|owner|active/i);
  for (const task_id of [undefined, "", "web23"]) {
    const invalid = evidenceFixture();
    invalid.context.exclusion.task_id = task_id;
    assert.throws(() => validateRunEvidence(invalid), /exclusion|owner|task/i);
  }
});

test("complete RUNNING inventory retains legitimate nonPROD jobs and permits only this PROD task's owned lease token", () => {
  const input = evidenceFixture();
  input.context.exclusion.running_ids.push("web23", "uiDesign");
  assert.ok(validateRunEvidence(input));
  input.context.exclusion.browser_lease_owner = "prodPerf-browser-unique";
  assert.ok(validateRunEvidence(input));
  input.context.exclusion.browser_lease_owner = "prodPerfOther";
  assert.throws(() => validateRunEvidence(input), /lease|owner|exclusion/i);
});

test("session verification uses a fresh injected clock so delayed preflight cannot accept an insufficient remaining lifetime", { timeout: 5000 }, async (t) => {
  const { origin } = await authUpstream(t, { expire: "2026-11-17T12:05:01+00:00" });
  let now = "2026-11-17T11:00:00Z";
  const batch = await createBatchSession({ origin, credentials: { username: "perf_alpha3", password: "password-secret" }, userAgent: "Mozilla/5.0 test-browser", ...batchTiming, clock: () => now, timeoutMs: 1000 });
  now = "2026-11-17T11:00:02Z";
  await assert.rejects(batch.verifySession(), /expiry|expires/i);
});

test("invalid batch timing is refused before creating a login/session row", { timeout: 5000 }, async (t) => {
  const { origin, observed } = await authUpstream(t);
  await assert.rejects(createBatchSession({ origin, credentials: { username: "perf_alpha3", password: "password-secret" }, userAgent: "Mozilla/5.0 test-browser", ...batchTiming, batchSeconds: 0, timeoutMs: 1000 }), /time|batch/i);
  assert.equal(observed.logins, 0);
});

test("legacy five-flag fixture verification cannot bypass the shared browser-preference readback", { timeout: 5000 }, async (t) => {
  const harness = await verifierHarness(t, 'client.request("GET", "/api/read")\nreturn {"exact_counts": True, "exact_ids": True, "geometry": True, "read_back": True, "runtime_manual_state": True}');
  await assert.rejects(verifyFixtureThroughSession({ manifest: {}, origin: "http://hub:3000", session: { getJson: async () => ({}) }, apiHarnessDir: harness, timeoutMs: 2000, maxRequests: 1 }), /preference|incomplete|verif/i);
});

test("browser planning requires the exact shared preference stratum rather than silently selecting system/profile defaults", () => {
  const plan = planBrowserBatch(routeConfig, routeManifest);
  assert.deepEqual(plan.browserPreferences, browserPreferences);
  for (const preferences of [undefined, { ...browserPreferences, theme: "system" }, { ...browserPreferences, display: { ...browserPreferences.display, board_animations: "desktop" } }]) {
    assert.throws(() => planBrowserBatch(routeConfig, { ...routeManifest, browser_preferences: preferences }), /preference|stratum|animation/i);
  }
});

test("bootstrap applies the declared theme before app scripts and exposes actual service-worker eligibility/control", () => {
  const c = collectorRealm();
  assert.equal(c.local.get("theme"), "light");
  const ready = c.events.find((event) => event.event === "collector_ready");
  assert.equal(ready.service_worker_supported, false);
  assert.equal(ready.service_worker_controlled, false);
  const unpinned = collectorRealm({ theme: "system" });
  assert.equal(unpinned.api.state().invalidReason, "preference_pin_mismatch");
});

test("a malformed latest final or multiple metric IDs cannot fall back to an older faster valid metric", () => {
  for (const tail of [
    { document_id: "d", name: "LCP", id: "l", value: NaN, final: true },
    { document_id: "d", name: "LCP", id: "other-lcp", value: 1, final: true },
  ]) {
    const result = summarizeMetrics([
      { document_id: "d", name: "LCP", id: "l", value: 200, final: true },
      { document_id: "d", name: "INP", id: "i", value: 24, final: true }, tail,
    ], { documentId: "d", hiddenObserved: true, inputVerified: true });
    assert.equal(result.complete, false);
    assert.equal(result.metrics.LCP, null);
    assert.deepEqual(result.missing, ["LCP"]);
  }
});

function documentObservation(documentId = "doc-one", { controlled = false } = {}) {
  return {
    document_id: documentId, ready_ms: 100, fresh_context: true, warm_cache_verified: controlled,
    events: [
      { record_type: "browser_lifecycle", event: "collector_ready", document_id: documentId, secure_context: true, initial_visibility: "visible", event_timing_supported: true, service_worker_supported: true, service_worker_controlled: controlled },
      { record_type: "browser_lifecycle", event: "trusted_input", document_id: documentId, document_ms: 1100, input_type: "click" },
      { record_type: "browser_lifecycle", event: "trusted_input", document_id: documentId, document_ms: 1150, input_type: "keydown" },
      { record_type: "browser_lifecycle", event: "trusted_input", document_id: documentId, document_ms: 1200, input_type: "click" },
      { record_type: "browser_diagnostic", diagnostic_type: "first-input", document_id: documentId, document_ms: 1210, entry: { entryType: "first-input", startTime: 1100, duration: 0, processingStart: 1100, processingEnd: 1100 } },
      { record_type: "browser_lifecycle", event: "post_action_settled", document_id: documentId, document_ms: 1250, frame_count: 2, idle_did_timeout: false },
      { record_type: "browser_lifecycle", event: "visibility", document_id: documentId, document_ms: 1300, visibility: "hidden", controlled: true },
      { record_type: "browser_metric", document_id: documentId, document_ms: 1101, name: "LCP", id: `lcp-${documentId}`, value: 250, final: true },
      { record_type: "browser_metric", document_id: documentId, document_ms: 1301, name: "INP", id: `inp-${documentId}`, value: 24, final: true },
    ],
    lifecycle: { hiddenObserved: true, trustedInputCount: 3, invalidReason: null, sinkFailed: false },
    actions: ["compose-open", "compose-type", "compose-cancel"].map((id) => ({ id, verified: true, trusted: true })),
    persisted_unchanged: true, network_errors: [], unexpected_api_writes: [],
  };
}

test("document validation derives metric completeness from actual callback/lifecycle/action records rather than a caller complete flag", () => {
  const plan = planBrowserBatch(routeConfig, routeManifest);
  const result = validateDocumentObservation(plan, documentObservation());
  assert.ok(result);
  assert.equal(result.complete, true);
  assert.equal(result.metrics.LCP.value, 250);
  assert.equal(result.metrics.INP.value, 24);
  const missing = documentObservation();
  missing.complete = true;
  missing.events = missing.events.filter((event) => event.name !== "INP");
  assert.throws(() => validateDocumentObservation(plan, missing), /INP|metric/i);
});

test("missing mandatory input, early first input, unexpected hide or sink failure invalidates a document", () => {
  const plan = planBrowserBatch(routeConfig, routeManifest);
  const absentAction = documentObservation();
  absentAction.actions = absentAction.actions.filter((action) => action.id !== "compose-type");
  assert.throws(() => validateDocumentObservation(plan, absentAction), /action|input/i);
  const early = documentObservation();
  early.events.find((event) => event.event === "trusted_input").document_ms = 1099;
  assert.throws(() => validateDocumentObservation(plan, early), /ready|window/i);
  for (const lifecycle of [{ hiddenObserved: false }, { invalidReason: "unexpected_hidden" }, { sinkFailed: true }]) {
    const invalid = documentObservation();
    Object.assign(invalid.lifecycle, lifecycle);
    assert.throws(() => validateDocumentObservation(plan, invalid), /lifecycle|hidden|sink/i);
  }
});

test("cold and warm-PWA cache evidence cannot be relabeled when the controller/fresh-context requirement is missing", () => {
  const cold = planBrowserBatch(routeConfig, routeManifest);
  const notFresh = documentObservation();
  notFresh.fresh_context = false;
  assert.throws(() => validateDocumentObservation(cold, notFresh), /fresh|context|cold/i);
  const warm = planBrowserBatch({ ...routeConfig, cache: "warm-pwa" }, routeManifest);
  assert.throws(() => validateDocumentObservation(warm, documentObservation()), /worker|controller|warm|cache/i);
  assert.equal(validateDocumentObservation(warm, documentObservation("warm", { controlled: true })).complete, true);
});

test("fast unauthorized responses, saved-state drift and a config write remain failed semantic samples", () => {
  const plan = planBrowserBatch(routeConfig, routeManifest);
  const unauthorized = documentObservation();
  unauthorized.network_errors.push({ status: 401, elapsed_ms: 1 });
  assert.throws(() => validateDocumentObservation(plan, unauthorized), /401|network|auth/i);
  const changed = documentObservation();
  changed.persisted_unchanged = false;
  assert.throws(() => validateDocumentObservation(plan, changed), /persist|fixture|state/i);
  const wrote = documentObservation();
  wrote.unexpected_api_writes.push({ method: "PUT", path: "/api/plugins/date_time/config" });
  assert.throws(() => validateDocumentObservation(plan, wrote), /write|mutat/i);
});

test("batch sampling is serial, keeps warmup separate, and verifies the same session outside document work", async () => {
  const plan = planBrowserBatch({ ...routeConfig, samples: 2, warmups: 1 }, routeManifest);
  let active = 0;
  let maximum = 0;
  let calls = 0;
  let verifications = 0;
  const records = [];
  const summary = await collectBatchSamples({ plan,
    verifySession: async () => { assert.equal(active, 0); verifications += 1; },
    verifyFixtureAfter: async () => verificationFlags,
    measureDocument: async () => { active += 1; maximum = Math.max(maximum, active); calls += 1; await new Promise(setImmediate); active -= 1; return documentObservation(`doc-${calls}`); },
    onRecord: (record) => records.push(record),
  });
  assert.ok(summary);
  assert.equal(summary.complete, true);
  assert.equal(summary.baseline_eligible, false);
  assert.equal(summary.samples, 2);
  assert.equal(summary.warmups, 1);
  assert.equal(maximum, 1);
  assert.equal(calls, 3);
  assert.equal(verifications, 6);
  assert.equal(records.filter((record) => record.record_type === "browser_warmup").length, 1);
  assert.equal(records.filter((record) => record.record_type === "browser_sample").length, 2);
});

test("a missing second sample metric preserves partial failure evidence and cannot become a complete batch", async () => {
  const plan = planBrowserBatch({ ...routeConfig, samples: 3 }, routeManifest);
  const records = [];
  let calls = 0;
  await assert.rejects(collectBatchSamples({ plan, verifySession: async () => {}, verifyFixtureAfter: async () => verificationFlags,
    measureDocument: async () => { calls += 1; const observation = documentObservation(`doc-${calls}`); if (calls === 2) observation.events = observation.events.filter((event) => event.name !== "INP"); return observation; },
    onRecord: (record) => records.push(record),
  }), /incomplete|INP|metric/i);
  assert.equal(calls, 2);
  assert.equal(records.filter((record) => record.record_type === "browser_sample").length, 1);
  assert.equal(records.filter((record) => record.record_type === "browser_failure").length, 1);
  assert.equal(records.find((record) => record.record_type === "browser_batch_summary").complete, false);
});

test("reusing a warmup or earlier document ID cannot fill another planned full-document sample", async () => {
  const plan = planBrowserBatch({ ...routeConfig, samples: 2 }, routeManifest);
  await assert.rejects(collectBatchSamples({ plan, verifySession: async () => {}, verifyFixtureAfter: async () => verificationFlags, measureDocument: async () => documentObservation("same-document"), onRecord: () => {} }), /document|duplicate|incomplete/i);
});

test("failed terminal fixture verification cannot leave a successful browser batch footer", async () => {
  const plan = planBrowserBatch(routeConfig, routeManifest);
  const records = [];
  await assert.rejects(collectBatchSamples({ plan, verifySession: async () => {}, verifyFixtureAfter: async () => { throw new Error("fixture changed after actions"); }, measureDocument: async () => documentObservation(), onRecord: (record) => records.push(record) }), /fixture|incomplete/i);
  const summaries = records.filter((record) => record.record_type === "browser_batch_summary");
  assert.equal(summaries.length, 1);
  assert.equal(summaries[0].complete, false);
});

test("foreground settling waits for native frame/idle turns and raw first-input proof without manufacturing final INP", async () => {
  const c = collectorRealm({ observerTypes: ["first-input"] });
  c.fire("click", { isTrusted: true });
  c.deliver("first-input", [{ entryType: "first-input", startTime: 25, duration: 0, processingStart: 25, processingEnd: 25 }]);
  await c.api.settleAfterActions({ timeoutMs: 1000 });
  await c.api.drain();
  assert.equal(c.scheduling.frames, 2);
  assert.equal(c.scheduling.idle, 1);
  const settled = c.events.find((event) => event.event === "post_action_settled");
  assert.ok(settled);
  assert.equal(settled.idle_did_timeout, false);
  assert.equal(c.events.some((event) => event.name === "INP"), false);
});

test("timed-out idle or missing first-input proof cannot be treated as a settled document", async () => {
  const idle = collectorRealm({ observerTypes: ["first-input"], idleTimedOut: true });
  idle.fire("click", { isTrusted: true });
  idle.deliver("first-input", [{ entryType: "first-input", startTime: 25, duration: 0 }]);
  await assert.rejects(idle.api.settleAfterActions({ timeoutMs: 1000 }), /idle|settle/i);
  const missing = collectorRealm();
  missing.fire("click", { isTrusted: true });
  await assert.rejects(missing.api.settleAfterActions({ timeoutMs: 1000 }), /first.input|settle/i);
});

test("a final callback without an observed pre-hide frame/idle settle mark is incomplete", () => {
  const plan = planBrowserBatch(routeConfig, routeManifest);
  const observation = documentObservation();
  observation.events = observation.events.filter((event) => event.event !== "post_action_settled");
  assert.throws(() => validateDocumentObservation(plan, observation), /settle|idle/i);
});

test("public CDP profile payloads preserve exact throttles and omit invalid desktop maxTouchPoints0", async () => {
  for (const profile of ["desktop", "phone"]) {
    const calls = [];
    const client = { send: async (method, payload) => { if (payload?.maxTouchPoints === 0) throw new Error("CDP rejects maxTouchPoints0"); calls.push({ method, payload }); } };
    const context = { newCDPSession: async () => client };
    const plan = planBrowserBatch({ ...routeConfig, profile }, routeManifest);
    const result = await applyBrowserProfile({ context, page: {}, plan, userAgent: "Mozilla/5.0 pinned" });
    assert.ok(result);
    assert.deepEqual(calls.find((call) => call.method === "Emulation.setTouchEmulationEnabled").payload, profile === "phone" ? { enabled: true, maxTouchPoints: 1 } : { enabled: false });
    assert.deepEqual(calls.find((call) => call.method === "Network.emulateNetworkConditions").payload, profile === "phone"
      ? { offline: false, latency: 150, downloadThroughput: 200000, uploadThroughput: 93750 }
      : { offline: false, latency: 20, downloadThroughput: 2500000, uploadThroughput: 1250000 });
    assert.equal(calls.some((call) => call.method === "Emulation.setFocusEmulationEnabled"), false);
  }
});

test("effective browser facts must match explicit locale/theme/geometry/reduced-motion and pinned UA before timing", () => {
  const plan = planBrowserBatch(routeConfig, routeManifest);
  const observed = { user_agent: "Mozilla/5.0 pinned", width: 1440, height: 900, dpr: 1, language: "en-US", timezone: "UTC", theme: "light", resolved_dark: false, reduced_motion: false, cookie_locale: "en", touch_points: 0, visibility: "visible", secure_context: true };
  assert.equal(validateEffectiveBrowser(plan, observed, "Mozilla/5.0 pinned"), true);
  for (const patch of [{ language: "en-GB" }, { theme: "system" }, { reduced_motion: true }, { width: 1280 }, { secure_context: false }]) {
    assert.throws(() => validateEffectiveBrowser(plan, { ...observed, ...patch }, "Mozilla/5.0 pinned"), /browser|preference|profile|context/i);
  }
});

test("persistent relay/session injection is bound to the same measured origin, seed, ownership and profile", () => {
  const evidence = validateRunEvidence(evidenceFixture());
  const plan = planBrowserBatch(routeConfig, routeManifest);
  const binding = { origin: "http://127.0.0.1:1234", target_origin: "http://hub:3000", seed_id: "seed-one", ownership_sha256: evidence.context.ownership_sha256, profile: "desktop" };
  const runtime = { relay: { origin: "http://127.0.0.1:1234", targetOrigin: "http://hub:3000" }, session: { binding: () => binding } };
  assert.equal(validateRuntimeBinding(runtime, evidence, plan), true);
  for (const patch of [{ origin: "http://127.0.0.1:5678" }, { seed_id: "other" }, { ownership_sha256: "other" }, { profile: "phone" }]) {
    assert.throws(() => validateRuntimeBinding({ ...runtime, session: { binding: () => ({ ...binding, ...patch }) } }, evidence, plan), /bind|origin|ownership|profile|seed/i);
  }
});

test("observation writer preserves partial records privately, redacts secrets and cannot overwrite an existing run", async (t) => {
  const directory = await temporaryDirectory(t);
  const file = path.join(directory, "events.jsonl");
  const writer = createObservationWriter({ path: file, runId: "actual-run", secrets: ["password-secret", "cookie-secret"] });
  assert.ok(writer && typeof writer.write === "function");
  writer.write({ schema_version: 99, run_id: "forged", record_type: "browser_error", error: "password-secret cookie-secret", headers: { Cookie: "cookie-secret" } });
  writer.close();
  const saved = JSON.parse((await readFile(file, "utf8")).trim());
  assert.equal(saved.schema_version, 1);
  assert.equal(saved.run_id, "actual-run");
  assert.equal(saved.error, "[REDACTED] [REDACTED]");
  assert.equal(saved.headers.Cookie, "[REDACTED]");
  assert.equal((await lstat(file)).mode & 0o777, 0o600);
  assert.throws(() => createObservationWriter({ path: file, runId: "other" }), /exist|EEXIST/i);
});

async function fakeChromeBinary(t, { publishPort = true } = {}) {
  const directory = await temporaryDirectory(t);
  const script = path.join(directory, "fake-chrome.mjs");
  await writeFile(script, `import fs from 'node:fs';import path from 'node:path';\nconst args=process.argv.slice(2);const profile=args.find(x=>x.startsWith('--user-data-dir=')).slice(16);\n${publishPort ? "fs.writeFileSync(path.join(profile,'DevToolsActivePort'),'9222\\n/devtools/browser/test\\n');" : ""}\nsetInterval(()=>{},1000);`);
  const seen = [];
  const spawnBrowser = (_binary, args, options) => { seen.push(args); return spawn(process.execPath, [script, ...args], options); };
  return { directory, seen, spawnBrowser };
}

test("owned Chromium startup attaches public noDefaults default context and removes only its private profile on close", { timeout: 5000 }, async (t) => {
  const fake = await fakeChromeBinary(t);
  const context = {};
  let attached;
  const chromium = { connectOverCDP: async (endpoint, options) => { attached = { endpoint, options }; return { contexts: () => [context], version: () => "156.0.fake", close: async () => {} }; } };
  const owner = await launchOwnedChromium({ chromium, executablePath: "/pinned/chromium", display: ":99", privateDirectoryParent: fake.directory, startupTimeoutMs: 1000, shutdownTimeoutMs: 500, spawnBrowser: fake.spawnBrowser });
  assert.ok(owner && owner.context);
  assert.equal(owner.context, context);
  assert.deepEqual(attached, { endpoint: "http://127.0.0.1:9222", options: { noDefaults: true } });
  assert.equal((await lstat(owner.profilePath)).mode & 0o777, 0o700);
  assert.equal(fake.seen[0].some((arg) => arg.startsWith("--headless")), false);
  await owner.close();
  await assert.rejects(lstat(owner.profilePath), /ENOENT/);
  assert.throws(() => process.kill(owner.pid, 0), /ESRCH/);
});

test("failed Chromium startup is bounded and cleans its owned process/profile before any sample can start", { timeout: 5000 }, async (t) => {
  const fake = await fakeChromeBinary(t, { publishPort: false });
  await assert.rejects(launchOwnedChromium({ chromium: { connectOverCDP: async () => { throw new Error("must not attach"); } }, executablePath: "/pinned/chromium", display: ":99", privateDirectoryParent: fake.directory, startupTimeoutMs: 250, shutdownTimeoutMs: 500, spawnBrowser: fake.spawnBrowser }), /startup|deadline|timeout/i);
  const profile = fake.seen[0]?.find((arg) => arg.startsWith("--user-data-dir="))?.slice(16);
  assert.ok(profile);
  await assert.rejects(lstat(profile), /ENOENT/);
});
