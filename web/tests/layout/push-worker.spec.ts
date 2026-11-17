import { expect, test } from "@playwright/test";

// Real notifications require full Chromium; the default headless shell has
// no notification service even when the Permissions API reports granted.
test.use({ channel: "chromium" });

const SCOPE_PATH = "/api/hassio_ingress/push-worker-test/";

test("the real ingress-scoped worker displays local push events and clears notifications", async ({
  page,
  context,
  baseURL,
}) => {
  const origin = new URL(baseURL!).origin;
  const scope = `${origin}${SCOPE_PATH}`;
  await context.grantPermissions(["notifications"], { origin });

  // Keep the existing fixture URL, without mounting unrelated product UI.
  await page.route("**/tests/layout/", (route) =>
    route.fulfill({
      contentType: "text/html",
      body: "<!doctype html><title>Push worker integration</title>",
    }),
  );
  await page.goto("/tests/layout/");
  expect(await page.evaluate(() => Notification.permission)).toBe("granted");

  const cdp = await context.newCDPSession(page);
  let registrationId = "";
  // The command/event shapes are defined by playwright-core/types/protocol.d.ts:
  // workerRegistrationUpdated supplies the browser's actual registration ID;
  // deliverPushMessage takes origin, registrationId and a serialized payload.
  cdp.on(
    "ServiceWorker.workerRegistrationUpdated",
    ({ registrations }: { registrations: Array<{ registrationId: string; scopeURL: string; isDeleted: boolean }> }) => {
      const registration = registrations.find((entry) => entry.scopeURL === scope && !entry.isDeleted);
      if (registration) registrationId = registration.registrationId;
    },
  );
  await cdp.send("ServiceWorker.enable");

  try {
    expect(
      await page.evaluate(async (scopePath) => {
        // The root script can register a narrower ingress scope. Its importScripts
        // fetches the real sw-shell-policy.js and sw-push.js from the Vite server.
        const registration = await navigator.serviceWorker.register("/sw.js", { scope: scopePath });
        const worker = registration.installing ?? registration.waiting ?? registration.active;
        if (!worker) throw new Error("The service worker was not created");
        if (worker.state !== "activated") {
          await new Promise<void>((resolve, reject) => {
            worker.addEventListener("statechange", () => {
              if (worker.state === "activated") resolve();
              else if (worker.state === "redundant") reject(new Error("The service worker failed to activate"));
            });
          });
        }
        return registration.scope;
      }, SCOPE_PATH),
    ).toBe(scope);
    await expect.poll(() => registrationId).not.toBe("");

    const notices = () =>
      page.evaluate(async (scopePath) => {
        const registration = await navigator.serviceWorker.getRegistration(scopePath);
        if (!registration) throw new Error("The push registration disappeared");
        return (await registration.getNotifications()).map((notice) => ({
          title: notice.title,
          body: notice.body,
          tag: notice.tag,
          data: notice.data,
        }));
      }, SCOPE_PATH);

    const clear = async (type: "CLEAR_BADGE" | "CLEAR_PUSH") => {
      await page.evaluate(
        async ({ scopePath, messageType }) => {
          const registration = await navigator.serviceWorker.getRegistration(scopePath);
          if (!registration?.active) throw new Error("The push worker is not active");
          registration.active.postMessage({ type: messageType });
        },
        { scopePath: SCOPE_PATH, messageType: type },
      );
    };

    // CDP injects a local browser push event directly into this registration;
    // no PushManager subscription or external push provider is involved.
    await cdp.send("ServiceWorker.deliverPushMessage", {
      origin,
      registrationId,
      data: JSON.stringify({
        title: "FiestaBoard",
        body: "A display needs attention.",
        tag: "worker-browser-test",
        url: "/settings?section=notifications",
        private: "must not persist",
      }),
    });
    const expected = [
      {
        title: "FiestaBoard",
        body: "A display needs attention.",
        tag: "worker-browser-test",
        data: { url: `${scope}settings?section=notifications` },
      },
    ];
    await expect.poll(notices).toEqual(expected);

    await clear("CLEAR_BADGE");
    await expect.poll(notices).toEqual(expected);
    await clear("CLEAR_PUSH");
    await expect.poll(notices).toEqual([]);

    await cdp.send("ServiceWorker.deliverPushMessage", {
      origin,
      registrationId,
      data: JSON.stringify({
        title: "Safe route",
        tag: "worker-browser-test",
        url: "https://external.example/private",
      }),
    });
    await expect.poll(notices).toEqual([
      {
        title: "Safe route",
        body: "",
        tag: "worker-browser-test",
        data: { url: scope },
      },
    ]);
    await clear("CLEAR_PUSH");
    await expect.poll(notices).toEqual([]);
  } finally {
    await page.evaluate(async (scopePath) => {
      const registration = await navigator.serviceWorker.getRegistration(scopePath);
      if (!registration) return;
      for (const notice of await registration.getNotifications()) notice.close();
      await registration.unregister();
      for (const name of await caches.keys()) {
        if (name.startsWith(`fb-scope-${encodeURIComponent(registration.scope)}-`)) await caches.delete(name);
      }
    }, SCOPE_PATH);
    await cdp.detach();
  }
});
