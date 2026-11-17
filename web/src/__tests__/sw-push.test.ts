/** Execute the real classic worker; only browser-owned APIs are simulated. */
import { readFileSync } from "node:fs";
import vm from "node:vm";

import { describe, expect, it } from "vitest";

const SCOPE = "https://hub.example/api/hassio_ingress/abc/";

type NotificationRecord = { title: string; options: { body?: string; tag?: string; data: { url: string } } };
type Client = { url: string; focus: () => Promise<unknown> };

function harness(scope = SCOPE, badgeMode = "supported") {
  const handlers: Record<string, (event: unknown) => void> = {};
  const shown: NotificationRecord[] = [];
  const opened: string[] = [];
  const focused: string[] = [];
  const badgeCalls: unknown[][] = [];
  const badgeClears: boolean[] = [];
  const closed: string[] = [];
  const waits: Promise<unknown>[] = [];
  let windows: Client[] = [];
  let notifications = [{ close: () => closed.push("existing") }];
  const navigator =
    badgeMode === "unsupported"
      ? {}
      : {
          setAppBadge: (...args: unknown[]) => {
            badgeCalls.push(args);
            if (badgeMode === "throw") throw new Error("badge unavailable");
            return badgeMode === "reject" ? Promise.reject(new Error("badge unavailable")) : Promise.resolve();
          },
          clearAppBadge: () => {
            badgeClears.push(true);
            if (badgeMode === "throw") throw new Error("badge unavailable");
            return badgeMode === "reject" ? Promise.reject(new Error("badge unavailable")) : Promise.resolve();
          },
        };
  const self = {
    location: new URL(scope),
    navigator,
    registration: {
      scope,
      showNotification: async (title: string, options: NotificationRecord["options"]) => {
        shown.push({ title, options });
      },
      getNotifications: async () => notifications,
    },
    clients: {
      matchAll: async (options: { type: string; includeUncontrolled: boolean }) => {
        expect(options).toEqual({ type: "window", includeUncontrolled: true });
        return windows;
      },
      openWindow: async (url: string) => {
        opened.push(url);
      },
    },
    addEventListener: (name: string, handler: (event: unknown) => void) => {
      handlers[name] = handler;
    },
  };
  const context = vm.createContext({
    self,
    navigator,
    URL,
    importScripts: (...paths: string[]) => {
      for (const path of paths) vm.runInContext(readFileSync(`public/${path.replace("./", "")}`, "utf8"), context);
    },
  });
  vm.runInContext(readFileSync("public/sw.js", "utf8"), context);

  async function dispatch(name: string, event: Record<string, unknown>) {
    const start = waits.length;
    expect(handlers[name], `${name} handler is registered by sw.js`).toBeTypeOf("function");
    handlers[name]({
      ...event,
      waitUntil: (promise: Promise<unknown>) => {
        waits.push(promise);
      },
    });
    expect(waits.length).toBeGreaterThan(start);
    await Promise.all(waits.slice(start));
  }

  return {
    shown,
    opened,
    focused,
    badgeCalls,
    badgeClears,
    closed,
    push: (payload: unknown) => dispatch("push", { data: { json: () => payload } }),
    malformed: () =>
      dispatch("push", {
        data: {
          json: () => {
            throw new Error("private malformed input");
          },
        },
      }),
    missing: () => dispatch("push", {}),
    click: (url?: unknown) =>
      dispatch("notificationclick", {
        notification: { data: { url }, close: () => closed.push("clicked") },
      }),
    message: (type: string) => dispatch("message", { data: { type } }),
    setWindows: (urls: string[], failFocus = false) => {
      windows = urls.map((url) => ({
        url,
        focus: async () => {
          if (failFocus) throw new Error("window gone");
          focused.push(url);
        },
      }));
    },
    failNotificationLookup: () => {
      self.registration.getNotifications = async () => {
        throw new Error("unavailable");
      };
    },
    failOneClose: () => {
      notifications = [
        {
          close: () => {
            throw new Error("gone");
          },
        },
        { close: () => closed.push("remaining") },
      ];
    },
  };
}

describe("push delivery", () => {
  it("shows the H15 fields without changing the app attention badge or persisting extra fields", async () => {
    const h = harness();
    await h.push({
      title: "FiestaBoard",
      body: "A display needs attention.",
      url: "/settings?section=notifications",
      tag: "display",
      unread: 42,
      secret: "private",
    });
    expect(h.shown).toEqual([
      {
        title: "FiestaBoard",
        options: {
          body: "A display needs attention.",
          tag: "display",
          data: { url: `${SCOPE}settings?section=notifications` },
        },
      },
    ]);
    expect(h.badgeCalls).toEqual([]);
  });

  it.each(["unsupported", "reject", "throw"])(
    "push cleanup leaves app attention unchanged when Badging is %s",
    async (mode) => {
      const h = harness(SCOPE, mode);
      await h.push({ title: "Alert", body: "Hello" });
      expect(h.shown[0].title).toBe("Alert");
      await h.message("CLEAR_PUSH");
      expect(h.badgeClears).toEqual([]);
    },
  );

  it.each([undefined, null, [], "private raw data", 42, { title: {}, body: { private: true }, tag: [] }])(
    "handles invalid payload %j without displaying raw data",
    async (payload) => {
      const h = harness();
      await h.push(payload);
      expect(h.shown).toEqual([{ title: "FiestaBoard", options: { body: "", data: { url: SCOPE } } }]);
    },
  );

  it("handles missing and malformed JSON with a generic notification", async () => {
    const h = harness();
    await h.missing();
    await h.malformed();
    expect(h.shown).toHaveLength(2);
    expect(h.shown.every((notice) => notice.title === "FiestaBoard" && notice.options.body === "")).toBe(true);
  });

  it("bounds notification text to the H15 limits", async () => {
    const h = harness();
    await h.push({ title: "a".repeat(81), body: "b".repeat(241), tag: "c".repeat(65) });
    expect(h.shown[0].title.length).toBeLessThanOrEqual(80);
    expect(h.shown[0].options.body!.length).toBeLessThanOrEqual(240);
    expect(h.shown[0].options.tag?.length ?? 0).toBeLessThanOrEqual(64);
  });

  it.each([
    ["/", SCOPE],
    ["pages/one", `${SCOPE}pages/one`],
    ["/api/hassio_ingress/abc/settings", `${SCOPE}settings`],
    ["https://external.example/", SCOPE],
    ["https://hub.example/outside/", SCOPE],
    ["//external.example/", SCOPE],
    ["javascript:alert(1)", SCOPE],
    ["../outside", SCOPE],
    ["/pages/../settings", SCOPE],
    ["/%2e%2e/outside", SCOPE],
    ["/%252e%252e/outside", SCOPE],
    ["/pages%2f..%2foutside", SCOPE],
    ["/\\external.example", SCOPE],
    ["/%5cexternal.example", SCOPE],
    ["/bad%escape", SCOPE],
    ["/" + "a".repeat(1024), SCOPE],
  ])("scopes payload URL %s safely", async (url, expected) => {
    const h = harness();
    await h.push({ title: "Alert", url });
    expect(h.shown[0].options.data.url).toBe(expected);
  });

  it("also routes root installations correctly", async () => {
    const h = harness("https://hub.example/");
    await h.push({ title: "Alert", url: "/pages" });
    expect(h.shown[0].options.data.url).toBe("https://hub.example/pages");
  });
});

describe("notification interaction", () => {
  it("closes the notification and focuses an exact same-app client", async () => {
    const h = harness();
    h.setWindows(["https://external.example/", "https://hub.example/", `${SCOPE}pages`]);
    await h.click(`${SCOPE}pages`);
    expect(h.focused).toEqual([`${SCOPE}pages`]);
    expect(h.opened).toEqual([]);
    expect(h.closed).toEqual(["clicked"]);
    expect(h.badgeClears).toEqual([]);
  });

  it("opens the scoped target when no matching client exists", async () => {
    const h = harness();
    h.setWindows([`${SCOPE}other`, "https://hub.example/api/hassio_ingress/other/pages"]);
    await h.click(`${SCOPE}pages`);
    expect(h.opened).toEqual([`${SCOPE}pages`]);
    expect(h.focused).toEqual([]);
  });

  it("opens the target if the matching client has gone away", async () => {
    const h = harness();
    h.setWindows([`${SCOPE}pages`], true);
    await h.click(`${SCOPE}pages`);
    expect(h.opened).toEqual([`${SCOPE}pages`]);
  });

  it.each([
    undefined,
    "https://external.example/",
    "https://hub.example/api/hassio_ingress/other/",
    `${SCOPE}../other`,
    `${SCOPE}%2e%2e/other`,
    "/\\external.example",
    "https://hub.example\\api\\hassio_ingress\\abc\\pages",
  ])("revalidates click data %s before opening", async (url) => {
    const h = harness();
    await h.click(url);
    expect(h.opened).toEqual([SCOPE]);
  });

  it("CLEAR_PUSH closes notifications without acknowledging More attention", async () => {
    const h = harness();
    await h.message("CLEAR_PUSH");
    expect(h.badgeClears).toEqual([]);
    expect(h.closed).toEqual(["existing"]);
  });

  it("notification lookup failure leaves More attention unchanged", async () => {
    const h = harness();
    h.failNotificationLookup();
    await h.message("CLEAR_PUSH");
    expect(h.badgeClears).toEqual([]);
  });

  it("closes remaining notifications if one close fails", async () => {
    const h = harness();
    h.failOneClose();
    await h.message("CLEAR_PUSH");
    expect(h.closed).toEqual(["remaining"]);
  });
});
