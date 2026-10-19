import { readFileSync } from "node:fs";
import vm from "node:vm";

import { expect, it } from "vitest";
it("holds worker activation until owned legacy caches are deleted and unregister completes", async () => {
  const events: Record<string, (event: unknown) => void> = {};
  const deleted: string[] = [];
  let unregister = false;
  let release!: () => void;
  const deletion = new Promise<void>((resolve) => {
    release = resolve;
  });
  const context = vm.createContext({
    self: {
      addEventListener: (name: string, callback: (event: unknown) => void) => {
        events[name] = callback;
      },
      skipWaiting: () => Promise.resolve(),
      registration: {
        scope: "http://localhost/board/",
        unregister: async () => {
          unregister = true;
        },
      },
      clients: { claim: async () => {} },
    },
    caches: {
      keys: async () => [
        "offlineCache",
        "fiestaboard-static-v2",
        "workbox-precache-v2-http://localhost/board/",
        "other-app",
      ],
      delete: async (name: string) => {
        await deletion;
        deleted.push(name);
        return true;
      },
    },
  });
  vm.runInContext(readFileSync("public/sw-auth-cache-cleanup.js", "utf8"), context);
  let completion: Promise<unknown> | undefined;
  events.activate({
    waitUntil: (promise: Promise<unknown>) => {
      completion = promise;
    },
  });
  expect(typeof completion?.then).toBe("function");
  expect(unregister).toBe(false);
  release();
  await completion;
  expect(deleted.sort()).toEqual([
    "fiestaboard-static-v2",
    "offlineCache",
    "workbox-precache-v2-http://localhost/board/",
  ]);
  expect(unregister).toBe(true);
  expect(events.fetch).toBeUndefined();
});
