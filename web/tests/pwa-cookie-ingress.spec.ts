/** Real HTTP cookies and the production worker; no request interception. */
import { readFileSync } from "node:fs";
import { createServer, type Server } from "node:http";

import { expect, test } from "@playwright/test";

let server: Server;
let origin: string;
const scope = "/ingress/cookie/";
const seen: Array<{ path: string; authenticated: boolean }> = [];

test.beforeAll(async () => {
  server = createServer((req, res) => {
    const path = req.url || "/";
    const authenticated = (req.headers.cookie || "").includes("ingress_session=valid");
    if (path === "/login") {
      res.setHeader("Set-Cookie", `ingress_session=valid; HttpOnly; SameSite=Lax; Path=${scope}`);
      res.end("signed in");
      return;
    }
    if (path === `${scope}sw.js` || path === `${scope}sw-shell-policy.js`) {
      res.setHeader("Content-Type", "application/javascript");
      res.end(readFileSync(`public/${path.split("/").pop()}`));
      return;
    }
    seen.push({ path, authenticated });
    if (path === `${scope}assets/redirect.js` && !authenticated) {
      res.writeHead(302, { Location: "/login" });
      res.end();
      return;
    }
    if (!authenticated && path !== `${scope}assets/public.js`) {
      res.writeHead(401);
      res.end("Unauthorized");
      return;
    }
    if (path.startsWith(`${scope}assets/`)) {
      res.setHeader("Content-Type", "application/javascript");
      if (path.endsWith("private.js")) res.setHeader("Cache-Control", "private");
      res.end('document.documentElement.dataset.booted = "yes"; export const loaded = true;');
      return;
    }
    res.setHeader("Content-Type", "text/html");
    res.end(
      `<!doctype html><title>Cookie ingress</title><h1>Protected page</h1><script type="module" src="${scope}assets/boot.js"></script>`,
    );
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") throw new Error("Missing HTTP port");
  origin = `http://127.0.0.1:${address.port}`;
});

test.afterAll(async () => {
  await new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve())));
});

test("cookie-gated page and uncached chunks load after activation without caching private data", async ({ page }) => {
  await page.goto(`${origin}/login`);
  await page.goto(`${origin}${scope}`);
  await expect(page.locator("html")).toHaveAttribute("data-booted", "yes");
  await page.evaluate(async (base) => {
    await navigator.serviceWorker.register(`${base}sw.js`);
    await navigator.serviceWorker.ready;
    if (!navigator.serviceWorker.controller) {
      await new Promise<void>((resolve) =>
        navigator.serviceWorker.addEventListener("controllerchange", () => resolve(), { once: true }),
      );
    }
  }, scope);
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-booted", "yes");
  for (const name of ["lazy", "private", "redirect", "public"]) {
    expect(
      await page.evaluate(
        async (url) => (await import(/* @vite-ignore */ url)).loaded,
        `${origin}${scope}assets/${name}.js`,
      ),
    ).toBe(true);
  }
  const cachedUrls = () =>
    page.evaluate(async () => {
      const cachesForOrigin = await caches.keys();
      return (
        await Promise.all(
          cachesForOrigin.map(async (name) => (await (await caches.open(name)).keys()).map((r) => r.url)),
        )
      ).flat();
    });
  // The public entry proves all preceding background cache attempts had a chance to finish.
  await expect.poll(cachedUrls).toContain(`${origin}${scope}assets/public.js`);
  expect(await cachedUrls()).toEqual([`${origin}${scope}assets/public.js`]);
  for (const name of ["boot", "lazy", "private", "redirect"]) {
    expect(seen).toContainEqual({ path: `${scope}assets/${name}.js`, authenticated: true });
    expect(seen).toContainEqual({ path: `${scope}assets/${name}.js`, authenticated: false });
  }
});
