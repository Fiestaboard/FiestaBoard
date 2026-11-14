/**
 * The app-shell service worker (public/sw.js + public/sw-shell-policy.js),
 * run in a vm with in-memory caches and a scripted network.
 *
 * The safety rules under test (web 2.8):
 * - nothing under the API is ever cached or answered by the worker;
 * - page loads are network-first, so an online tab never gets a stale shell;
 * - the cached shell is used only when the network fails;
 * - older FiestaBoard caches are deleted on activate.
 */
import { readFileSync } from "node:fs";
import vm from "node:vm";

import { beforeEach, describe, expect, it, vi } from "vitest";

const SCOPE = "https://hub.example/ingress/abc/";

type Policy = {
  SHELL_CACHE: string;
  ASSET_CACHE: string;
  MAX_ASSETS: number;
  classify: (req: Record<string, unknown>) => string;
  isStorable: (res: Record<string, unknown>) => boolean;
  isShell: (res: Record<string, unknown>) => boolean;
  shellAssets: (html: string, scope: string) => string[];
  isObsoleteCache: (name: string, scope: string) => boolean;
};

function loadPolicy(scope = SCOPE): Policy {
  const self: Record<string, unknown> = { registration: { scope } };
  vm.runInNewContext(readFileSync("public/sw-shell-policy.js", "utf8"), { self, URL });
  return self.fbShellPolicy as Policy;
}

const req = (over: Record<string, unknown> = {}) => ({
  method: "GET",
  mode: "cors",
  sameOrigin: true,
  hasAuthorization: false,
  pathname: "/ingress/abc/assets/app-123.js",
  scopePath: "/ingress/abc/",
  ...over,
});

describe("sw-shell-policy: classify", () => {
  const P = loadPolicy();

  it.each([
    ["an encoded API traversal", req({ pathname: "/ingress/abc/assets/%2e%2e%2fapi/status" }), "bypass"],
    ["a no-store request", req({ cache: "no-store" }), "bypass"],
    ["an API GET", req({ pathname: "/ingress/abc/api/v1/status" }), "bypass"],
    ["the API root", req({ pathname: "/ingress/abc/api" }), "bypass"],
    ["an API navigation", req({ pathname: "/ingress/abc/api/docs", mode: "navigate" }), "bypass"],
    ["a POST", req({ method: "POST" }), "bypass"],
    ["a cross-origin GET", req({ sameOrigin: false }), "bypass"],
    ["a request with Authorization", req({ hasAuthorization: true }), "bypass"],
    ["a path outside the scope", req({ pathname: "/other/assets/x.js" }), "bypass"],
    ["sw.js itself", req({ pathname: "/ingress/abc/sw.js" }), "bypass"],
    ["manifest.json", req({ pathname: "/ingress/abc/manifest.json" }), "bypass"],
    ["a page load", req({ pathname: "/ingress/abc/pages", mode: "navigate" }), "navigate"],
    ["a hashed build file", req(), "asset"],
    ["an icon", req({ pathname: "/ingress/abc/icons/icon-192x192.png" }), "asset"],
  ])("%s → %s", (_name, request, expected) => {
    expect(P.classify(request)).toBe(expected);
  });
});

describe("sw-shell-policy: what may be stored", () => {
  const P = loadPolicy();
  const ok = {
    status: 200,
    type: "basic",
    redirected: false,
    cacheControl: "",
    contentType: "text/html; charset=utf-8",
  };

  it("stores a plain 200 same-origin response", () => {
    expect(P.isStorable(ok)).toBe(true);
    expect(P.isShell(ok)).toBe(true);
  });
  it.each([
    ["no-store", { ...ok, cacheControl: "no-store" }],
    ["private", { ...ok, cacheControl: "private, max-age=60" }],
    ["an error", { ...ok, status: 500 }],
    ["a partial", { ...ok, status: 206 }],
    ["an opaque response", { ...ok, type: "opaque" }],
    ["a redirected asset", { ...ok, redirected: true }],
  ])("never stores %s", (_name, res) => {
    expect(P.isStorable(res)).toBe(false);
  });
  it("takes only HTML that was not a redirect as the shell", () => {
    expect(P.isShell({ ...ok, redirected: true })).toBe(false);
    expect(P.isShell({ ...ok, contentType: "application/json" })).toBe(false);
  });
  it("finds the shell's build files, resolved against the scope, once each", () => {
    const html =
      '<link rel="modulepreload" href="/ingress/abc/assets/a-1.js"><script src="/ingress/abc/assets/a-1.js"></script>' +
      '<link href="/ingress/abc/assets/root-2.css" rel="stylesheet"><link rel="icon" href="/ingress/abc/icons/x.png">';
    expect(P.shellAssets(html, SCOPE)).toEqual([`${SCOPE}assets/a-1.js`, `${SCOPE}assets/root-2.css`]);
  });
  it("only preloads assets within this app scope", () => {
    expect(
      P.shellAssets(
        '<script src="https://other.example/assets/a.js"></script><script src="/other/assets/b.js"></script><script src="assets/c.js"></script>',
        SCOPE,
      ),
    ).toEqual([`${SCOPE}assets/c.js`]);
  });
  it("marks older FiestaBoard caches obsolete and leaves its own and other apps' alone", () => {
    expect(P.isObsoleteCache(P.SHELL_CACHE, SCOPE)).toBe(false);
    expect(P.isObsoleteCache(P.ASSET_CACHE, SCOPE)).toBe(false);
    expect(P.isObsoleteCache("fb-shell-v0", SCOPE)).toBe(false);
    expect(P.isObsoleteCache("offlineCache", SCOPE)).toBe(false);
    expect(P.isObsoleteCache("fiestaboard-static-v2", SCOPE)).toBe(false);
    expect(P.isObsoleteCache(`workbox-precache-v2-${SCOPE}`, SCOPE)).toBe(true);
    expect(P.isObsoleteCache("workbox-precache-v2-https://other/", SCOPE)).toBe(false);
    expect(P.isObsoleteCache("other-app", SCOPE)).toBe(false);
  });
});

/* ---------- the worker itself ---------- */

class MemoryCache {
  entries = new Map<string, Response>();
  async match(key: Request | string) {
    const hit = this.entries.get(typeof key === "string" ? key : key.url);
    return hit ? hit.clone() : undefined;
  }
  async put(key: Request | string, res: Response) {
    this.entries.set(typeof key === "string" ? key : key.url, res);
  }
  async keys() {
    return [...this.entries.keys()].map((url) => new Request(url));
  }
  async delete(key: Request | string) {
    return this.entries.delete(typeof key === "string" ? key : key.url);
  }
}

function harness(scope = SCOPE, stores = new Map<string, MemoryCache>()) {
  const handlers: Record<string, (e: unknown) => void> = {};
  const network: Array<(r: Request) => Response | undefined> = [];
  let online = true;
  const fetched: string[] = [];
  const caches = {
    open: async (name: string) => {
      if (!stores.has(name)) stores.set(name, new MemoryCache());
      return stores.get(name)!;
    },
    keys: async () => [...stores.keys()],
    delete: async (name: string) => stores.delete(name),
    match: async (key: Request, opts?: { cacheName?: string }) => {
      const names = opts?.cacheName ? [opts.cacheName] : [...stores.keys()];
      for (const n of names) {
        const hit = await stores.get(n)?.match(key);
        if (hit) return hit;
      }
      return undefined;
    },
  };
  const fetchImpl = async (input: Request | string, init?: RequestInit) => {
    const r = new Request(input, init);
    fetched.push(r.url);
    if (!online) throw new TypeError("Failed to fetch");
    for (const route of network) {
      const res = route(r);
      // A same-origin fetch is "basic"; a constructed Response says "default".
      if (res) return Object.defineProperty(res, "type", { value: "basic" });
    }
    return new Response("not found", { status: 404 });
  };
  const self = {
    location: new URL(scope),
    registration: { scope },
    clients: { claim: async () => {} },
    skipWaiting: async () => {},
    addEventListener: (name: string, cb: (e: unknown) => void) => {
      handlers[name] = cb;
    },
  };
  const context = vm.createContext({
    self,
    caches,
    fetch: fetchImpl,
    Request,
    Response,
    URL,
    importScripts: (path: string) => {
      vm.runInContext(readFileSync(`public/${path.replace("./", "")}`, "utf8"), context);
    },
  });
  vm.runInContext(readFileSync("public/sw.js", "utf8"), context);

  async function lifecycle(name: "install" | "activate") {
    let wait: Promise<unknown> = Promise.resolve();
    handlers[name]({ waitUntil: (p: Promise<unknown>) => (wait = p) });
    await wait;
  }

  /** Dispatch a fetch; resolves to the worker's answer, or "network" when it stayed out. */
  async function dispatch(url: string, init: RequestInit & { mode?: RequestMode } = {}): Promise<Response | "network"> {
    const { mode, ...rest } = init;
    const request = new Request(url, rest);
    // Request() refuses mode "navigate"; the worker only reads it, so shadow it.
    if (mode) Object.defineProperty(request, "mode", { value: mode });
    let answer = null as Promise<Response> | null;
    const extra: Promise<unknown>[] = [];
    handlers.fetch({
      request,
      respondWith: (p: Promise<Response>) => (answer = p),
      waitUntil: (p: Promise<unknown>) => extra.push(p),
    });
    if (!answer) return "network" as const;
    const res = await answer;
    await Promise.all(extra);
    return res;
  }

  return {
    stores,
    caches,
    fetched,
    network,
    setOnline: (v: boolean) => (online = v),
    lifecycle,
    dispatch,
    allCachedUrls: () => [...stores.values()].flatMap((c) => [...c.entries.keys()]),
  };
}

const html = (marker: string) =>
  new Response(
    `<!doctype html><title>${marker}</title><script type="module" src="/ingress/abc/assets/entry-1.js"></script>`,
    {
      headers: { "content-type": "text/html", "cache-control": "no-cache, must-revalidate" },
    },
  );

describe("sw.js", () => {
  let h: ReturnType<typeof harness>;
  beforeEach(() => {
    h = harness();
    let build = "build-1";
    h.network.push((r) => (r.url === SCOPE || r.url.startsWith(`${SCOPE}pages`) ? html(build) : undefined));
    h.network.push((r) =>
      r.url.includes("/assets/") ? new Response("js", { headers: { "content-type": "text/javascript" } }) : undefined,
    );
    h.network.push((r) =>
      r.url.includes("/api/")
        ? new Response(JSON.stringify({ username: "maya" }), {
            headers: { "content-type": "application/json", "cache-control": "no-store" },
          })
        : undefined,
    );
    (h as unknown as { setBuild: (b: string) => void }).setBuild = (b) => (build = b);
  });

  it("caches the shell and its build files on install", async () => {
    await h.lifecycle("install");
    expect(h.allCachedUrls().sort()).toEqual([SCOPE, `${SCOPE}assets/entry-1.js`]);
  });

  it("never caches personalized navigation HTML", async () => {
    h.network.unshift((r) => (r.url.endsWith("account") ? html("PRIVATE ACCOUNT") : undefined));
    await h.lifecycle("install");
    await h.dispatch(`${SCOPE}account`, { mode: "navigate" });
    h.setOnline(false);
    const res = await h.dispatch(`${SCOPE}pages`, { mode: "navigate" });
    expect(await (res as Response).text()).not.toContain("PRIVATE ACCOUNT");
  });

  it("fetches cacheable shell resources without credentials", async () => {
    const credentials: string[] = [];
    h.network.unshift((r) => {
      credentials.push(r.credentials);
      return undefined;
    });
    await h.lifecycle("install");
    expect(credentials.length).toBeGreaterThan(0);
    expect(credentials.every((value) => value === "omit")).toBe(true);
  });

  it("never answers or caches an API request, signed in or not", async () => {
    await h.lifecycle("install");
    expect(await h.dispatch(`${SCOPE}api/auth/status`)).toBe("network");
    expect(await h.dispatch(`${SCOPE}api/v1/pages`, { headers: { authorization: "Bearer t" } })).toBe("network");
    expect(await h.dispatch(`${SCOPE}api/board/current-message`, { mode: "navigate" })).toBe("network");
    expect(h.allCachedUrls().some((u) => u.includes("/api/"))).toBe(false);
  });

  it("serves page loads from the network while online, refreshing the shell", async () => {
    await h.lifecycle("install");
    (h as unknown as { setBuild: (b: string) => void }).setBuild("build-2");
    const res = await h.dispatch(`${SCOPE}pages`, { mode: "navigate" });
    expect(res).not.toBe("network");
    expect(await (res as Response).text()).toContain("build-2");
    const shell = await h.stores.get(loadPolicy().SHELL_CACHE)!.match(SCOPE);
    expect(await shell!.text()).toContain("build-2");
  });

  it("falls back to the cached shell only when the network fails", async () => {
    await h.lifecycle("install");
    h.setOnline(false);
    const res = await h.dispatch(`${SCOPE}schedule`, { mode: "navigate" });
    expect(await (res as Response).text()).toContain("build-1");
  });

  it("fails an offline page load honestly when no shell was ever cached", async () => {
    h.setOnline(false);
    await h.lifecycle("install");
    await expect(h.dispatch(`${SCOPE}`, { mode: "navigate" })).rejects.toThrow("Failed to fetch");
  });

  it("serves a cached build file without the network", async () => {
    await h.lifecycle("install");
    h.setOnline(false);
    const res = await h.dispatch(`${SCOPE}assets/entry-1.js`);
    expect(await (res as Response).text()).toBe("js");
  });

  it("does not keep a build file the server marked no-store", async () => {
    h.network.unshift((r) =>
      r.url.endsWith("secret.js") ? new Response("x", { headers: { "cache-control": "no-store" } }) : undefined,
    );
    await h.dispatch(`${SCOPE}assets/secret.js`);
    expect(h.allCachedUrls()).not.toContain(`${SCOPE}assets/secret.js`);
  });

  it("preserves credentials online without caching the private response", async () => {
    h.network.unshift((r) =>
      r.url.endsWith("protected.js")
        ? new Response(r.credentials === "omit" ? "denied" : "private chunk", {
            status: r.credentials === "omit" ? 401 : 200,
          })
        : undefined,
    );
    const response = await h.dispatch(`${SCOPE}assets/protected.js`, { credentials: "include" });
    expect((response as Response).status).toBe(200);
    expect(await (response as Response).text()).toBe("private chunk");
    expect(h.allCachedUrls()).not.toContain(`${SCOPE}assets/protected.js`);
  });

  it.each(["open", "match", "put"] as const)("serves online assets when cache %s fails", async (operation) => {
    const cache = await h.caches.open(loadPolicy().ASSET_CACHE);
    if (operation === "open") vi.spyOn(h.caches, "open").mockRejectedValue(new Error("storage unavailable"));
    else vi.spyOn(cache, operation).mockRejectedValue(new Error("storage unavailable"));
    const response = await h.dispatch(`${SCOPE}assets/new.js`);
    expect(await (response as Response).text()).toBe("js");
    expect(h.fetched).toContain(`${SCOPE}assets/new.js`);
  });

  it("isolates activation and eviction across two ingress scopes", async () => {
    const otherScope = "https://hub.example/ingress/other/";
    const other = harness(otherScope, h.stores);
    other.network.push(() => new Response("other boot"));
    await other.dispatch(`${otherScope}assets/boot.js`);
    const legacy = new MemoryCache();
    h.stores.set("fb-assets-v2", legacy);
    const obsolete = loadPolicy().ASSET_CACHE.replace("v3", "v0");
    h.stores.set(obsolete, new MemoryCache());
    await h.lifecycle("activate");
    expect(h.stores.has(obsolete)).toBe(false);
    expect(h.stores.get("fb-assets-v2")).toBe(legacy);
    for (let i = 0; i <= loadPolicy().MAX_ASSETS; i++) await h.dispatch(`${SCOPE}assets/chunk-${i}.js`);
    other.setOnline(false);
    const response = await other.dispatch(`${otherScope}assets/boot.js`);
    expect(await (response as Response).text()).toBe("other boot");
    expect(h.stores.has(loadPolicy(otherScope).ASSET_CACHE)).toBe(true);
  });

  it("stores only the independent anonymous asset, without caller headers", async () => {
    h.network.unshift((r) =>
      r.url.endsWith("variant.js")
        ? new Response(r.credentials === "omit" && !r.headers.has("x-account") ? "public" : "private")
        : undefined,
    );
    const url = `${SCOPE}assets/variant.js`;
    expect(await ((await h.dispatch(url, { headers: { "x-account": "account" } })) as Response).text()).toBe("private");
    h.setOnline(false);
    expect(await ((await h.dispatch(url)) as Response).text()).toBe("public");
  });

  it("does not cache redirected anonymous assets", async () => {
    h.network.unshift((r) =>
      r.url.endsWith("redirect.js")
        ? Object.defineProperty(new Response("login"), "redirected", { value: true })
        : undefined,
    );
    await h.dispatch(`${SCOPE}assets/redirect.js`);
    expect(h.allCachedUrls()).not.toContain(`${SCOPE}assets/redirect.js`);
  });

  it("keeps at most MAX_ASSETS build files, dropping the oldest", async () => {
    const P = loadPolicy();
    for (let i = 0; i <= P.MAX_ASSETS; i++) await h.dispatch(`${SCOPE}assets/chunk-${i}.js`);
    const cached = [...h.stores.get(loadPolicy().ASSET_CACHE)!.entries.keys()];
    expect(cached).toHaveLength(P.MAX_ASSETS);
    expect(cached).not.toContain(`${SCOPE}assets/chunk-0.js`);
  });
});
