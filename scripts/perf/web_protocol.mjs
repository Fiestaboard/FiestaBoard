import { createHash } from "node:crypto";
import http from "node:http";
import https from "node:https";
import { isDeepStrictEqual } from "node:util";

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
  const ids = { LCP: new Set(), INP: new Set() };
  const invalid = { LCP: false, INP: false };
  for (const record of records) {
    if (record.document_id !== documentId || record.final !== true || !Object.hasOwn(metrics, record.name)) continue;
    if (typeof record.id !== "string" || !record.id || typeof record.value !== "number" || !Number.isFinite(record.value) || record.value < 0) invalid[record.name] = true;
    ids[record.name].add(record.id);
    if (ids[record.name].size !== 1) invalid[record.name] = true;
    metrics[record.name] = invalid[record.name] ? null : { id: record.id, value: record.value };
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

const offsetDate = (value) => typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) ? Date.parse(value) : NaN;

export function validateBatchTiming({ nowUtc, batchSeconds, marginSeconds }) {
  const now = offsetDate(nowUtc);
  if (!Number.isFinite(now) || !Number.isFinite(batchSeconds) || batchSeconds <= 0 || !Number.isFinite(marginSeconds) || marginSeconds < 0) {
    throw new Error("Explicit batch time and expiry margin are required");
  }
  return now;
}

export function validateSessionBatch(snapshot, { nowUtc, batchSeconds, marginSeconds, expectedCount }) {
  const now = validateBatchTiming({ nowUtc, batchSeconds, marginSeconds });
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

const publishedSource = "83236253aa8103db856b7efa456e088b9c9ec548";
const publishedPlatforms = {
  arm64: { manifest: "sha256:e0127d1f0eed00e13cd394f098580c2b96579b458731b6dc5d7ee842c7645886", image: "sha256:ddf771f44a75dde50288922b9d38c75b88aad0c4449ccef2a5d896c790825cae" },
  amd64: { manifest: "sha256:62764744c42302386ed746a93c8ca15ee7464b75a436a8cc6acb2e9be675a9e3", image: "sha256:84fce4473f73cf77a81974314ba4382043fec2d49cce955cdffdbe4b84b2a683" },
};

export function validateRunEvidence({ manifestBytes, ownershipBytes, context, targetOrigin, nowUtc, maxAgeSeconds, diagnostic }) {
  if (createHash("sha256").update(manifestBytes).digest("hex") !== context?.manifest_sha256) throw new Error("Public manifest file hash mismatch");
  if (createHash("sha256").update(ownershipBytes).digest("hex") !== context?.ownership_sha256) throw new Error("Ownership file hash mismatch");
  const manifest = JSON.parse(manifestBytes.toString());
  const ownership = JSON.parse(ownershipBytes.toString());
  if (context.schema_version !== 1 || manifest.schema_version !== 1 || typeof context.run_id !== "string" || !context.run_id) throw new Error("Invalid run evidence schema or identity binding");
  if ([manifest.source_commit, ownership.source_commit, context.source_commit].some((source) => source !== publishedSource)) throw new Error("Published source identity mismatch");
  if (!manifest.seed_id || manifest.seed_id !== ownership.seed_id || manifest.seed_id !== context.seed_id) throw new Error("Seed identity binding mismatch");
  if (!ownership.data_dir || ownership.data_dir !== context.data_dir) throw new Error("Synthetic data directory binding mismatch");
  if (ownership.empty_before_start !== true || !Array.isArray(ownership.prestart_entries) || ownership.prestart_entries.length !== 0) throw new Error("Synthetic store was not attested empty before startup");
  const normalizeOrigin = (value) => {
    const url = new URL(value);
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.pathname !== "/" || url.search || url.hash) throw new Error("Target must be a credential-free HTTP(S) origin");
    return url.origin;
  };
  const origin = normalizeOrigin(targetOrigin);
  if ([manifest.base_url, ownership.base_url, context.target_origin].some((value) => normalizeOrigin(value) !== origin)) throw new Error("Target origin binding mismatch");
  if (!context.container || context.container.id !== ownership.container_id) throw new Error("Container identity binding mismatch");
  const platform = publishedPlatforms[context.container.architecture];
  if (!platform || context.container.manifest_digest !== platform.manifest || ownership.image_manifest !== platform.manifest || context.container.image_id !== platform.image) throw new Error("Published platform image/manifest/architecture mismatch");
  const now = Date.parse(nowUtc);
  if (!Number.isFinite(now) || !Number.isFinite(maxAgeSeconds) || maxAgeSeconds <= 0) throw new Error("Explicit evidence freshness time and maximum age are required");
  for (const value of [context.captured_utc, context.exclusion?.checked_utc]) {
    const time = Date.parse(value);
    if (!Number.isFinite(time) || time > now || now - time > maxAgeSeconds * 1000) throw new Error("Stale or future run/inventory observation; fresh evidence required");
  }
  const exclusion = context.exclusion;
  const taskId = exclusion.task_id;
  const lease = exclusion.browser_lease_owner;
  const inventory = exclusion.running_ids;
  const activeProd = Array.isArray(inventory) ? inventory.filter((id) => typeof id === "string" && id.startsWith("prod")) : [];
  const ownedLease = typeof taskId === "string" && typeof lease === "string" && (lease === taskId || (lease.startsWith(`${taskId}-`) && lease.length > taskId.length + 1));
  if (typeof taskId !== "string" || !taskId.startsWith("prod") || !Array.isArray(inventory) || !inventory.every((id) => typeof id === "string" && id.length > 0) || activeProd.length !== 1 || activeProd[0] !== taskId || !ownedLease || !Array.isArray(exclusion.container_names) || exclusion.container_names.length > 3 || exclusion.container_names.length === 0) throw new Error("Missing/competing active PROD task or owned browser lease exclusion");
  if (!context.host || !Array.isArray(context.host.unavailable)) throw new Error("Host identity or explicit unavailable fields missing");
  if (diagnostic !== true) throw new Error("Baseline calibration evidence validation is not implemented; only explicit diagnostics are currently executable");
  return { manifest, ownership, context, diagnostic: true };
}

export function collectorMetadataFromProvenance(provenance) {
  const integrity = "sha512-ArI3kx5jI0atlTtmV0fWU3fjpLmq/nD3Zr1iFFlJLaqa5wLBkUSzINwBPySCX/8jRyjlmy1Volw1kz1g9XE4Jg==";
  const sha256 = "397a8cffdeec35be161d00e3ed1378a644223f710dafee49584d376a64d3b9a0";
  if (provenance?.version !== "5.1.0" || provenance.name !== "web-vitals") throw new Error("Collector package version/name pin mismatch");
  if (provenance.verified_integrity !== true || provenance.npm_integrity !== integrity) throw new Error("Verified official npm integrity is required");
  if (provenance.tarball_sha256 !== "5a508f690262ddacd4937f7fcb2f15f020fa94c47aad0d47af1f716296144d61") throw new Error("Official tarball pin mismatch");
  const member = provenance.members?.["package/dist/web-vitals.attribution.iife.js"];
  if (member?.sha256 !== sha256 || member.bytes !== 11582) throw new Error("Packaged collector digest/size pin mismatch");
  if (provenance.license !== "Apache-2.0" || provenance.registry_metadata_url !== "https://registry.npmjs.org/web-vitals/5.1.0" || provenance.tarball_url !== "https://registry.npmjs.org/web-vitals/-/web-vitals-5.1.0.tgz") throw new Error("Official collector provenance mismatch");
  return { version: "5.1.0", attribution: true, format: "iife", license: "Apache-2.0", package_integrity: integrity, sha256 };
}

const approvedBrowserPreferences = { theme: "light", locale: "en-US", next_locale: "en", timezone: "UTC", display: { reduce_motion: false, board_animations: "on", site_animations: "on", board_flap_speed: "standard" } };

export function planBrowserBatch(config, manifest) {
  const profile = profileFor(config.profile);
  if (!isDeepStrictEqual(manifest.browser_preferences, approvedBrowserPreferences)) throw new Error("Manifest browser preference/animation stratum must match the approved explicit pin");
  if (!["flagship", "note", "array", "panel"].includes(config.geometry) || !manifest.boards?.[config.geometry]) throw new Error("Unknown fixture geometry");
  const board = manifest.boards[config.geometry];
  const page = manifest.pages?.find((item) => item.id === board.page_ids?.[0] && item.geometry === config.geometry && item.kind === "literal");
  if (!page) throw new Error("The geometry's first literal page is missing");
  const paths = { home: "/", pages: "/pages", editor: `/pages/edit/${encodeURIComponent(page.id)}`, schedule: "/schedule", integrations: "/integrations", appearance: "/settings/appearance" };
  if (!Object.hasOwn(paths, config.route)) throw new Error("Unknown browser route");
  if (!["cold-browser", "warm-pwa"].includes(config.cache)) throw new Error("Explicit cold-browser or warm-pwa cache stratum required");
  if (!Number.isInteger(config.samples) || config.samples < 1 || (config.diagnostic !== true && config.samples < 20)) throw new Error("Invalid sample count; baseline batches require at least20");
  if (!Number.isInteger(config.batch) || config.batch < 1) throw new Error("Explicit positive batch number required");
  const warmups = config.warmups ?? 1;
  if (!Number.isInteger(warmups) || warmups < 0 || (config.diagnostic !== true && warmups < 1)) throw new Error("Invalid warmup count");
  const filter = config.library_filter ?? "all";
  if (!["all", "selected-board"].includes(filter)) throw new Error("Unknown library filter case");
  return {
    profileName: config.profile, profile, browserPreferences: structuredClone(manifest.browser_preferences), geometry: config.geometry, route: config.route, cache: config.cache,
    batch: config.batch, samples: config.samples, warmups, diagnostic: config.diagnostic === true,
    board, page, path: paths[config.route], preferences: { boardId: board.id, libraryFilter: filter === "all" ? "all" : board.id },
    expectedLibraryCount: filter === "all" ? 96 : 24,
  };
}

export function buildCollectorInitScript(source, preferences) {
  return `${source.toString()}\n;window.webVitals = webVitals;\n;(${installBrowserCollector.toString()})(${JSON.stringify(preferences)});\n`;
}

export function validateDocumentObservation(plan, observation) {
  if (typeof observation?.document_id !== "string" || !observation.document_id || !Number.isFinite(observation.ready_ms) || observation.ready_ms < 0) throw new Error("Document identity and actual route-ready timing are required");
  const events = observation.events;
  if (!Array.isArray(events) || events.some((event) => event.document_id !== observation.document_id)) throw new Error("Document events must be scoped to the current document");
  const ready = events.filter((event) => event.event === "collector_ready");
  if (ready.length !== 1 || ready[0].secure_context !== true || ready[0].initial_visibility !== "visible" || ready[0].event_timing_supported !== true) throw new Error("Secure foreground collector/Event Timing readiness is incomplete");
  if (ready[0].service_worker_supported !== true) throw new Error("Service worker eligibility is unavailable");
  if (plan.cache === "cold-browser" && (observation.fresh_context !== true || ready[0].service_worker_controlled !== false)) throw new Error("Cold-browser sample lacks fresh uncontrolled context evidence");
  if (plan.cache === "warm-pwa" && (ready[0].service_worker_controlled !== true || observation.warm_cache_verified !== true)) throw new Error("Warm-PWA controller/cache evidence is missing");
  const lifecycle = observation.lifecycle;
  if (!lifecycle || lifecycle.hiddenObserved !== true || lifecycle.invalidReason !== null || lifecycle.sinkFailed !== false) throw new Error("Document lifecycle/hidden/sink evidence is incomplete");
  const hidden = events.filter((event) => event.event === "visibility" && event.visibility === "hidden" && event.controlled === true);
  if (hidden.length !== 1 || !Number.isFinite(hidden[0].document_ms)) throw new Error("Exactly one actual controlled hidden lifecycle event is required");
  const settled = events.filter((event) => event.event === "post_action_settled");
  if (!settled.length || settled.some((event) => event.frame_count !== 2 || event.idle_did_timeout !== false || !Number.isFinite(event.document_ms))) throw new Error("Observed native frame/idle settle before hidden is required");
  const latestSettle = [...settled].sort((left, right) => left.document_ms - right.document_ms).at(-1);
  if (latestSettle.document_ms >= hidden[0].document_ms) throw new Error("Settle must precede the actual hidden transition");
  if (!events.some((event) => event.diagnostic_type === "first-input" && event.entry?.entryType === "first-input")) throw new Error("Actual raw first-input proof is missing from settle evidence");
  const inputs = events.filter((event) => event.event === "trusted_input");
  if (!inputs.length || inputs.length !== lifecycle.trustedInputCount || inputs.some((event) => !Number.isFinite(event.document_ms))) throw new Error("Actual trusted input records are missing or inconsistent");
  const firstInput = Math.min(...inputs.map((event) => event.document_ms));
  if (latestSettle.document_ms < Math.max(...inputs.map((event) => event.document_ms)) || latestSettle.trusted_input_count !== inputs.length) throw new Error("Latest settle must follow every trusted input in the script");
  if (firstInput - observation.ready_ms < 1000) throw new Error("First trusted input preceded the fixed post-ready observation window");
  const scripts = {
    home: ["compose-open", "compose-type", "compose-cancel"], pages: ["page-open"],
    editor: ["editor-focus", "editor-type", "editor-undo"], schedule: ["schedule-open", "schedule-cancel"],
    integrations: ["integration-configure", "integration-cancel"], appearance: ["theme-change", "theme-restore"],
  };
  const required = [...scripts[plan.route], ...(plan.profileName === "phone" ? ["more-open", "more-close"] : [])];
  if (!Array.isArray(observation.actions) || observation.actions.length !== required.length || observation.actions.some((action, index) => action.id !== required[index] || action.verified !== true || action.trusted !== true) || inputs.length < required.length) throw new Error("Mandatory trusted action script is missing, reordered or unverified");
  if (observation.persisted_unchanged !== true) throw new Error("Persisted fixture state changed or was not verified");
  if (!Array.isArray(observation.unexpected_api_writes) || observation.unexpected_api_writes.length) throw new Error("Unexpected API write/mutation invalidates the document");
  if (!Array.isArray(observation.network_errors) || observation.network_errors.length) throw new Error("Network/authentication errors (including401) invalidate the document");
  const metrics = summarizeMetrics(events.filter((event) => event.record_type === "browser_metric"), { documentId: observation.document_id, hiddenObserved: true, inputVerified: true });
  if (!metrics.complete) throw new Error(`Final document metric callbacks missing/invalid: ${metrics.missing.join(",")}`);
  for (const metric of events.filter((event) => event.record_type === "browser_metric" && event.final === true)) {
    const boundary = metric.name === "INP" ? hidden[0].document_ms : firstInput;
    if (!Number.isFinite(metric.document_ms) || metric.document_ms < boundary) throw new Error("Final metric callback preceded its actual lifecycle boundary");
  }
  return { complete: true, document_id: observation.document_id, ready_ms: observation.ready_ms, metrics: metrics.metrics, action_count: required.length, cache: plan.cache };
}

export function validateRuntimeBinding(runtime, evidence, plan) {
  if (!runtime?.relay || typeof runtime.session?.binding !== "function") throw new Error("Paired owned relay/session binding required");
  const binding = runtime.session.binding();
  if (new URL(runtime.relay.origin).hostname !== "127.0.0.1" || runtime.relay.targetOrigin !== evidence.context.target_origin || binding.origin !== runtime.relay.origin || binding.target_origin !== evidence.context.target_origin) throw new Error("Runtime origin/relay binding mismatch");
  if (binding.seed_id !== evidence.manifest.seed_id || binding.ownership_sha256 !== evidence.context.ownership_sha256 || binding.profile !== plan.profileName) throw new Error("Runtime seed/ownership/profile binding mismatch");
  return true;
}

export function validateEffectiveBrowser(plan, observed, userAgent) {
  const expected = {
    user_agent: userAgent, width: plan.profile.viewport.width, height: plan.profile.viewport.height, dpr: plan.profile.deviceScaleFactor,
    language: plan.browserPreferences.locale, timezone: plan.browserPreferences.timezone, theme: "light", resolved_dark: false,
    reduced_motion: false, cookie_locale: plan.browserPreferences.next_locale, touch_points: plan.profile.hasTouch ? 1 : 0, visibility: "visible", secure_context: true,
  };
  if (!Object.entries(expected).every(([key, value]) => observed?.[key] === value)) throw new Error("Effective browser/profile/context preferences mismatch");
  return true;
}

// Serialized into the measured document; no module closures may be referenced.
export function installBrowserCollector(preferences) {
  if (window.top !== window || !["http:", "https:"].includes(window.location.protocol)) return null;
  if (window.__perfBrowser) throw new Error("Collector already installed in this document");
  const documentId = window.crypto.randomUUID();
  const state = { documentId, trustedInputCount: 0, hiddenObserved: false, invalidReason: null, sinkFailed: false, firstInputCount: 0, lastEventStart: null, postActionSettled: false, lastSettledInputCount: null };
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
  const diagnostic = (entry, type) => {
    if (type === "first-input") state.firstInputCount += 1;
    if (type === "event" && Number.isFinite(entry.startTime)) state.lastEventStart = Math.max(state.lastEventStart ?? -Infinity, entry.startTime);
    emit({ record_type: "browser_diagnostic", diagnostic_type: type, entry: serializeEntry(entry) });
  };
  if (window.document.visibilityState !== "visible") invalidate("document_not_foreground");
  if (preferences.theme !== "light") invalidate("preference_pin_mismatch");
  try {
    if (preferences.theme === "light") window.localStorage.setItem("theme", "light");
    window.localStorage.setItem("fiestaboard_current_board", preferences.boardId);
    window.localStorage.setItem("fiestaboard_pages_view_mode", "grid");
    window.sessionStorage.setItem("fiestaboard_pages_display_filter", preferences.libraryFilter);
  } catch {
    invalidate("preference_storage_unavailable");
  }
  const api = {
    state: () => ({ ...state }),
    settleAfterActions: async ({ timeoutMs = 10000 } = {}) => {
      if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || state.invalidReason || state.trustedInputCount < 1 || window.document.visibilityState !== "visible") throw new Error("Foreground trusted-input lifecycle required for settle");
      if (typeof window.requestAnimationFrame !== "function" || typeof window.requestIdleCallback !== "function") throw new Error("Native frame/idle APIs unavailable for settle");
      let timer;
      let frameHandle;
      let idleHandle;
      let cancelled = false;
      let frames = 0;
      const inputGeneration = state.trustedInputCount;
      const frame = () => new Promise((resolve) => {
        frameHandle = window.requestAnimationFrame(() => { if (!cancelled) { frames += 1; resolve(); } });
      });
      const work = async () => {
        await frame();
        await frame();
        await new Promise((resolve, reject) => {
          idleHandle = window.requestIdleCallback((deadline) => {
            if (cancelled) return;
            if (deadline.didTimeout) reject(new Error("Native idle callback timed out; document not settled"));
            else resolve();
          }, { timeout: timeoutMs });
        });
        if (cancelled || state.invalidReason || window.document.visibilityState !== "visible") throw new Error("Lifecycle changed during foreground settle");
        if (state.trustedInputCount !== inputGeneration) throw new Error("New trusted input arrived during settle; fresh barrier required");
        for (const { observer, type } of observers) for (const entry of observer.takeRecords()) diagnostic(entry, type);
        await api.drain();
        if (state.firstInputCount < 1) throw new Error("Raw first-input proof missing at settle");
        if (state.trustedInputCount !== inputGeneration) throw new Error("New trusted input arrived before settle acknowledgement");
        if (state.invalidReason) throw new Error("Sink/lifecycle failed during settle");
        state.postActionSettled = true;
        state.lastSettledInputCount = inputGeneration;
        emit({ record_type: "browser_lifecycle", event: "post_action_settled", frame_count: frames, idle_did_timeout: false, trusted_input_count: inputGeneration, first_input_count: state.firstInputCount, last_event_start_ms: state.lastEventStart });
        await api.drain();
        if (state.invalidReason) throw new Error("Sink/lifecycle failed after settle acknowledgement");
        if (state.trustedInputCount !== inputGeneration) throw new Error("New trusted input arrived during settle acknowledgement");
        return { ...state };
      };
      const timeout = new Promise((_resolve, reject) => {
        timer = window.setTimeout(() => { cancelled = true; reject(new Error("Foreground settle deadline exceeded")); }, timeoutMs);
      });
      try {
        return await Promise.race([work(), timeout]);
      } catch (error) {
        cancelled = true;
        state.postActionSettled = false;
        invalidate("post_action_settle_failed");
        emit({ record_type: "browser_lifecycle", event: "post_action_settle_failed" });
        throw error;
      } finally {
        window.clearTimeout(timer);
        if (frameHandle !== undefined) window.cancelAnimationFrame(frameHandle);
        if (idleHandle !== undefined) window.cancelIdleCallback(idleHandle);
      }
    },
    beforeHide: () => {
      if (window.document.visibilityState !== "visible" || state.hiddenObserved) invalidate("unexpected_hidden");
      if (!state.postActionSettled || state.lastSettledInputCount !== state.trustedInputCount || state.trustedInputCount < 1) invalidate("post_action_unsettled");
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
      state.postActionSettled = false;
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
        for (const entry of observer.takeRecords()) diagnostic(entry, type);
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
  for (const type of ["largest-contentful-paint", "event", "first-input"]) {
    if (!supported.includes(type)) continue;
    try {
      const observer = new window.PerformanceObserver((list) => {
        for (const entry of list.getEntries()) diagnostic(entry, type);
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
    service_worker_supported: Boolean(window.navigator?.serviceWorker), service_worker_controlled: Boolean(window.navigator?.serviceWorker?.controller),
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
