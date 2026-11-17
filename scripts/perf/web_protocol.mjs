import { createHash } from "node:crypto";
import http from "node:http";
import https from "node:https";

// No network, browser, or filesystem side effects occur on import.
export function profileFor(name) {
  if (name === "desktop") {
    return {
      viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1, isMobile: false, hasTouch: false,
      cpuThrottlingRate: 1,
      network: { offline: false, latency: 20, downloadThroughput: 2500000, uploadThroughput: 1250000 },
    };
  }
  if (name === "phone") {
    return {
      viewport: { width: 390, height: 844 }, deviceScaleFactor: 3, isMobile: true, hasTouch: true,
      cpuThrottlingRate: 4,
      network: { offline: false, latency: 150, downloadThroughput: 200000, uploadThroughput: 93750 },
    };
  }
  throw new Error(`Unknown browser profile: ${name}`);
}

export function summarizeMetrics(records, { documentId, hiddenObserved, inputVerified }) {
  const metrics = { LCP: null, INP: null };
  for (const record of records) {
    if (record.document_id !== documentId || record.final !== true || !Object.hasOwn(metrics, record.name)) continue;
    if (typeof record.id !== "string" || !record.id || typeof record.value !== "number" || !Number.isFinite(record.value) || record.value < 0) continue;
    metrics[record.name] = { id: record.id, value: record.value };
  }
  const missing = Object.keys(metrics).filter((name) => metrics[name] === null);
  return { complete: missing.length === 0 && hiddenObserved === true && inputVerified === true, metrics, missing };
}

const secretKey = /^(?:credentials|password|authorization|proxy-authorization|cookie|set-cookie|session|session_cookie|token|secret|local_api_key|cloud_key|note_array_token)$/i;

export function redact(value, secrets = []) {
  if (typeof value === "string") {
    let clean = value;
    for (const secret of secrets.filter((item) => typeof item === "string" && item.length > 0).sort((a, b) => b.length - a.length)) {
      clean = clean.split(secret).join("[REDACTED]");
    }
    return clean;
  }
  if (Array.isArray(value)) return value.map((item) => redact(item, secrets));
  if (value instanceof Error) return redact({ name: value.name, message: value.message }, secrets);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, secretKey.test(key) ? "[REDACTED]" : redact(item, secrets)]));
  }
  return value;
}

// Verifies supplied bytes/declarations; package provenance is a separate root
// attestation prerequisite, not something a self-declared digest can establish.
export function verifyCollector(source, metadata) {
  if (metadata?.version !== "5.1.0") throw new Error("Collector version must be 5.1.0");
  if (metadata.attribution !== true || metadata.format !== "iife") throw new Error("Collector must be the attribution IIFE build");
  if (typeof metadata.package_integrity !== "string" || !metadata.package_integrity) throw new Error("Collector package integrity is missing");
  if (metadata.license !== "Apache-2.0") throw new Error("Collector license provenance is missing");
  const digest = createHash("sha256").update(source).digest("hex");
  if (digest !== metadata.sha256) throw new Error("Collector SHA-256 digest mismatch");
  return true;
}

export function relayLocation(location, { upstreamOrigin, relayOrigin }) {
  const upstream = new URL(upstreamOrigin);
  const destination = new URL(location, upstream);
  if (destination.origin !== upstream.origin) return { location, allowed: false };
  if (!/^(?:[a-z][a-z0-9+.-]*:)?\/\//i.test(location)) return { location, allowed: true };
  return { location: `${new URL(relayOrigin).origin}${destination.pathname}${destination.search}${destination.hash}`, allowed: true };
}

export function relayRequestHeaders(headers, { upstreamOrigin, relayOrigin }) {
  const upstream = new URL(upstreamOrigin);
  const relay = new URL(relayOrigin);
  const forwarded = { ...endToEndHeaders(headers), host: upstream.host };
  for (const key of ["origin", "referer"]) {
    if (typeof forwarded[key] !== "string") continue;
    try {
      const value = new URL(forwarded[key]);
      if (value.origin !== relay.origin) continue;
      if (key === "origin") {
        if (value.pathname === "/" && !value.search && !value.hash) forwarded[key] = upstream.origin;
      } else forwarded[key] = `${upstream.origin}${value.pathname}${value.search}${value.hash}`;
    } catch {
      // Invalid/foreign values remain invalid/foreign at the upstream gate.
    }
  }
  return forwarded;
}

export function validateSessionBatch(snapshot, { nowUtc, batchSeconds, marginSeconds, expectedCount }) {
  const offsetDate = (value) => typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? Date.parse(value) : NaN;
  const now = offsetDate(nowUtc);
  if (!Number.isFinite(now) || !Number.isFinite(batchSeconds) || batchSeconds <= 0 || !Number.isFinite(marginSeconds) || marginSeconds < 0) {
    throw new Error("Explicit batch time and expiry margin are required");
  }
  if (!Array.isArray(snapshot?.sessions) || snapshot.sessions.length === 0 || snapshot.sessions.length > 200) throw new Error("Invalid session count");
  if (expectedCount !== undefined && snapshot.sessions.length !== expectedCount) throw new Error("Session count changed during the batch");
  const current = snapshot.sessions.filter((row) => row.id === snapshot.current_session_id);
  if (current.length !== 1) throw new Error("Exactly one current session must exist");
  if (current[0].kind !== "browser") throw new Error("The current session must be a real browser session");
  const expiry = offsetDate(current[0].expires_at);
  if (!Number.isFinite(expiry) || expiry <= now + (batchSeconds + marginSeconds) * 1000) throw new Error("Session expiry does not exceed the batch and margin");
  return { session_count: snapshot.sessions.length, current_expires_at: current[0].expires_at, kind: "browser" };
}

export function validateSessionCookieHeaders(headers) {
  const values = headers.filter((value) => /^fiestaboard_session=/.test(value));
  if (values.length !== 1) throw new Error("Exactly one genuine session cookie is required");
  const attributes = new Map(values[0].split(";").slice(1).map((part) => {
    const [key, ...rest] = part.trim().split("=");
    return [key.toLowerCase(), rest.join("=").toLowerCase()];
  }));
  if (attributes.has("domain")) throw new Error("Explicit Domain cookies require a separate reviewed transport; no rewrite allowed");
  if (!attributes.has("httponly") || attributes.get("samesite") !== "lax" || attributes.get("path") !== "/") throw new Error("Session cookie must retain HttpOnly, SameSite=lax and Path=/");
  return { hostOnly: true, httpOnly: true, sameSite: "lax", secure: attributes.has("secure") };
}

// Serialized into the measured document; no module closures may be referenced.
export function installBrowserCollector(preferences) {
  if (window.top !== window || !["http:", "https:"].includes(window.location.protocol)) return null;
  if (window.__perfBrowser) throw new Error("Collector already installed in this document");
  const documentId = window.crypto.randomUUID();
  const state = { documentId, trustedInputCount: 0, hiddenObserved: false, invalidReason: null, sinkFailed: false };
  const pending = new Set();
  const observers = [];
  let hideArmed = false;
  const invalidate = (reason) => { state.invalidReason ??= reason; };
  const scalarFields = (source, keys) => Object.fromEntries(keys.flatMap((key) => {
    const value = source?.[key];
    return typeof value === "string" || typeof value === "boolean" || (typeof value === "number" && Number.isFinite(value)) ? [[key, value]] : [];
  }));
  const serializeEntry = (entry) => scalarFields(entry, [
    "entryType", "name", "startTime", "duration", "interactionId", "processingStart", "processingEnd", "renderTime", "loadTime", "size", "url", "identifier",
  ]);
  const emit = (record) => {
    const payload = { document_id: documentId, document_ms: window.performance.now(), ...record };
    let acknowledgement;
    try {
      acknowledgement = Promise.resolve(window.__perfMetric(payload));
    } catch {
      state.sinkFailed = true;
      invalidate("sink_failed");
      return;
    }
    const completed = acknowledgement.catch(() => {
      state.sinkFailed = true;
      invalidate("sink_failed");
    }).finally(() => pending.delete(completed));
    pending.add(completed);
  };
  if (window.document.visibilityState !== "visible") invalidate("document_not_foreground");
  try {
    window.localStorage.setItem("fiestaboard_current_board", preferences.boardId);
    window.localStorage.setItem("fiestaboard_pages_view_mode", "grid");
    window.sessionStorage.setItem("fiestaboard_pages_display_filter", preferences.libraryFilter);
  } catch {
    invalidate("preference_storage_unavailable");
  }
  const api = {
    state: () => ({ ...state }),
    beforeHide: () => {
      if (window.document.visibilityState !== "visible" || state.hiddenObserved) invalidate("unexpected_hidden");
      hideArmed = true;
    },
    drain: async () => {
      while (pending.size) await Promise.all([...pending]);
      return { ...state };
    },
  };
  window.__perfBrowser = api;
  for (const type of ["click", "keydown"]) {
    window.addEventListener(type, (event) => {
      if (!event.isTrusted) return;
      if (window.document.visibilityState !== "visible" || state.hiddenObserved) invalidate("input_after_hidden");
      state.trustedInputCount += 1;
      emit({ record_type: "browser_lifecycle", event: "trusted_input", input_type: type });
    }, { capture: true });
  }
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) {
      invalidate("bfcache_restore");
      emit({ record_type: "browser_lifecycle", event: "bfcache_restore" });
    }
  }, { capture: true });
  window.addEventListener("visibilitychange", (event) => {
    const visibility = window.document.visibilityState;
    if (!event.isTrusted) return;
    if (visibility === "hidden") {
      if (!hideArmed || state.hiddenObserved) invalidate("unexpected_hidden");
      if (hideArmed) state.hiddenObserved = true;
      for (const { observer, type } of observers) {
        for (const entry of observer.takeRecords()) emit({ record_type: "browser_diagnostic", diagnostic_type: type, entry: serializeEntry(entry) });
      }
    } else if (state.hiddenObserved) invalidate("visible_after_final_flush");
    emit({ record_type: "browser_lifecycle", event: "visibility", visibility, controlled: hideArmed });
  }, { capture: true });

  const report = (metric) => {
    const final = !state.invalidReason && (metric.name === "LCP"
      ? state.trustedInputCount > 0 || state.hiddenObserved
      : metric.name === "INP" && state.hiddenObserved && state.trustedInputCount > 0);
    emit({
      record_type: "browser_metric", final: Boolean(final),
      ...scalarFields(metric, ["name", "id", "value", "delta", "rating", "navigationType"]),
      entries: Array.from(metric.entries ?? [], serializeEntry),
      attribution: scalarFields(metric.attribution, [
        "target", "url", "timeToFirstByte", "resourceLoadDelay", "resourceLoadDuration", "elementRenderDelay",
        "interactionTarget", "interactionTime", "interactionType", "loadState", "inputDelay", "processingDuration", "presentationDelay", "nextPaintTime",
      ]),
    });
  };
  // Final-only official reporters avoid a duplicate-value suppression problem
  // with reportAllChanges:true. Raw observers below are diagnostics, never INP.
  window.webVitals.onLCP(report, { reportAllChanges: false });
  window.webVitals.onINP(report, { reportAllChanges: false, durationThreshold: 16 });
  const supported = window.PerformanceObserver?.supportedEntryTypes ?? [];
  for (const type of ["largest-contentful-paint", "event"]) {
    if (!supported.includes(type)) continue;
    try {
      const observer = new window.PerformanceObserver((list) => {
        for (const entry of list.getEntries()) emit({ record_type: "browser_diagnostic", diagnostic_type: type, entry: serializeEntry(entry) });
      });
      observer.observe({ type, buffered: true, ...(type === "event" ? { durationThreshold: 16 } : {}) });
      observers.push({ observer, type });
    } catch {
      emit({ record_type: "browser_lifecycle", event: "observer_unavailable", diagnostic_type: type });
    }
  }
  emit({
    record_type: "browser_lifecycle", event: "collector_ready", secure_context: window.isSecureContext === true,
    time_origin: window.performance.timeOrigin, initial_visibility: window.document.visibilityState,
    event_timing_supported: Boolean(window.PerformanceEventTiming && "interactionId" in window.PerformanceEventTiming.prototype),
  });
  return api;
}

const hopHeaders = new Set(["connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer", "transfer-encoding", "upgrade"]);

function endToEndHeaders(headers) {
  const excluded = new Set(hopHeaders);
  for (const token of String(headers.connection ?? "").split(",")) excluded.add(token.trim().toLowerCase());
  return Object.fromEntries(Object.entries(headers).filter(([key]) => !excluded.has(key.toLowerCase())));
}

export async function createRelay({ targetUrl, requestTimeoutMs = 10000 }) {
  const target = new URL(targetUrl);
  if (!["http:", "https:"].includes(target.protocol) || target.username || target.password || target.pathname !== "/" || target.search || target.hash) {
    throw new Error("Relay target must be an HTTP(S) origin without credentials or a path");
  }
  const transport = target.protocol === "https:" ? https : http;
  const connections = new Set();
  let origin;
  const server = http.createServer((req, res) => {
    const headers = relayRequestHeaders(req.headers, { upstreamOrigin: target.origin, relayOrigin: origin });
    const outgoing = transport.request(target, { method: req.method, path: req.url, headers, agent: false }, (incoming) => {
      const responseHeaders = endToEndHeaders(incoming.headers);
      if (typeof responseHeaders.location === "string") {
        responseHeaders.location = relayLocation(responseHeaders.location, { upstreamOrigin: target.origin, relayOrigin: origin }).location;
      }
      res.writeHead(incoming.statusCode, incoming.statusMessage, responseHeaders);
      incoming.once("error", () => res.destroy());
      incoming.pipe(res);
    });
    outgoing.setTimeout(requestTimeoutMs, () => outgoing.destroy(new Error("upstream request deadline")));
    outgoing.once("error", () => {
      if (res.headersSent) res.destroy();
      else {
        res.writeHead(502, { "Content-Type": "text/plain", "Cache-Control": "no-store" });
        res.end("Upstream transport failure");
      }
    });
    req.once("aborted", () => outgoing.destroy());
    req.pipe(outgoing);
  });
  server.on("connection", (socket) => {
    connections.add(socket);
    socket.once("close", () => connections.delete(socket));
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  origin = `http://127.0.0.1:${server.address().port}`;
  return {
    origin,
    close: () => new Promise((resolve, reject) => {
      server.close((error) => error ? reject(error) : resolve());
      for (const socket of connections) socket.destroy();
    }),
  };
}
