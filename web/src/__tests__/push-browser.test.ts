import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { pushApi } from "@/lib/api/push";
import { clearBrowserPush, enableBrowserPush, getPushAvailability, readBrowserPush } from "@/lib/pwa/push";

vi.mock("@/lib/api/push", () => ({ pushApi: { subscribe: vi.fn() } }));

const key = "B" + "A".repeat(86);
const keyBytes = Uint8Array.from(atob(key.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
const status = { user_enabled: true, device_enabled: true, subscribed: true };
let permission: NotificationPermission;
let requestPermission: ReturnType<typeof vi.fn>;
let subscription: ReturnType<typeof makeSubscription> | null;
let subscribe: ReturnType<typeof vi.fn>;
let registration: ServiceWorkerRegistration;
let getRegistration: ReturnType<typeof vi.fn>;

function makeSubscription() {
  return {
    options: { applicationServerKey: keyBytes.buffer },
    expirationTime: null,
    toJSON: () => ({ endpoint: "https://web.push.apple.com/example", keys: { p256dh: "public", auth: "secret" } }),
    unsubscribe: vi.fn().mockResolvedValue(true),
  };
}

beforeEach(() => {
  permission = "default";
  requestPermission = vi.fn().mockImplementation(async () => (permission = "granted"));
  vi.stubGlobal("isSecureContext", true);
  vi.stubGlobal("Notification", {
    get permission() {
      return permission;
    },
    requestPermission,
  });
  vi.stubGlobal("PushManager", function () {});
  subscription = null;
  subscribe = vi.fn().mockImplementation(async () => (subscription = makeSubscription()));
  registration = {
    scope: new URL("/", location.href).href,
    active: { postMessage: vi.fn() },
    pushManager: { getSubscription: vi.fn(async () => subscription), subscribe },
    getNotifications: vi.fn().mockResolvedValue([]),
  } as unknown as ServiceWorkerRegistration;
  getRegistration = vi.fn().mockImplementation(async () => registration);
  Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { getRegistration } });
  vi.mocked(pushApi.subscribe).mockResolvedValue(status as Awaited<ReturnType<typeof pushApi.subscribe>>);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
  Reflect.deleteProperty(navigator, "serviceWorker");
  Reflect.deleteProperty(window, "__reactRouterContext");
});

describe("push enrollment", () => {
  it("reads permission without requesting it or enrolling on load", async () => {
    expect(await readBrowserPush()).toEqual({ permission: "default", subscribed: false });
    expect(requestPermission).not.toHaveBeenCalled();
    expect(subscribe).not.toHaveBeenCalled();
    expect(pushApi.subscribe).not.toHaveBeenCalled();
  });

  it("requests permission synchronously from the user gesture before async registration work", async () => {
    const work = enableBrowserPush(key);
    expect(requestPermission).toHaveBeenCalledOnce();
    expect(getRegistration).not.toHaveBeenCalled();
    await expect(work).resolves.toEqual(status);
    expect(subscribe).toHaveBeenCalledWith({ userVisibleOnly: true, applicationServerKey: keyBytes });
    expect(pushApi.subscribe).toHaveBeenCalledWith(subscription!.toJSON());
  });

  it.each(["default", "denied"] as const)("does not subscribe when permission is %s", async (result) => {
    requestPermission.mockResolvedValue(result);
    await expect(enableBrowserPush(key)).rejects.toMatchObject({ code: result });
    expect(subscribe).not.toHaveBeenCalled();
  });

  it("does not re-prompt denied permission", async () => {
    permission = "denied";
    await expect(enableBrowserPush(key)).rejects.toMatchObject({ code: "denied" });
    expect(requestPermission).not.toHaveBeenCalled();
  });

  it("re-registers a matching browser subscription for the current server session", async () => {
    permission = "granted";
    subscription = makeSubscription();
    await enableBrowserPush(key);
    expect(subscribe).not.toHaveBeenCalled();
    expect(pushApi.subscribe).toHaveBeenCalledWith(subscription.toJSON());
  });

  it("replaces a subscription whose VAPID key belongs to an old hub", async () => {
    permission = "granted";
    const old = makeSubscription();
    old.options.applicationServerKey = new Uint8Array(65).buffer;
    subscription = old;
    await enableBrowserPush(key);
    expect(old.unsubscribe).toHaveBeenCalledOnce();
    expect(subscribe).toHaveBeenCalledOnce();
  });

  it("rolls back new browser enrollment when the server rejects it", async () => {
    vi.mocked(pushApi.subscribe).mockRejectedValue(new Error("offline"));
    await expect(enableBrowserPush(key)).rejects.toThrow();
    expect(subscription!.unsubscribe).toHaveBeenCalledOnce();
  });

  it("does not delete a preexisting subscription when session registration fails", async () => {
    subscription = makeSubscription();
    vi.mocked(pushApi.subscribe).mockRejectedValue(new Error("conflict"));
    await expect(enableBrowserPush(key)).rejects.toThrow();
    expect(subscription.unsubscribe).not.toHaveBeenCalled();
  });

  it("looks up the exact ingress scope and never unsubscribes a parent worker", async () => {
    Object.assign(window, { __reactRouterContext: { basename: "/api/hassio_ingress/token/" } });
    subscription = makeSubscription();
    await clearBrowserPush();
    expect(getRegistration).toHaveBeenCalledWith("/api/hassio_ingress/token/");
    expect(subscription.unsubscribe).not.toHaveBeenCalled();
    expect(registration.active!.postMessage).not.toHaveBeenCalled();
  });

  it("unsubscribes and tells the app worker to clear notifications on sign-out", async () => {
    subscription = makeSubscription();
    await clearBrowserPush();
    expect(subscription.unsubscribe).toHaveBeenCalledOnce();
    expect(registration.active!.postMessage).toHaveBeenCalledWith({ type: "CLEAR_PUSH" });
  });

  it("still clears worker notifications when unsubscribing throws", async () => {
    subscription = makeSubscription();
    subscription.unsubscribe.mockRejectedValue(new Error("browser storage unavailable"));
    await clearBrowserPush();
    expect(registration.active!.postMessage).toHaveBeenCalledWith({ type: "CLEAR_PUSH" });
  });

  it("returns a truthful insecure state even if API shims exist", async () => {
    vi.stubGlobal("isSecureContext", false);
    expect(getPushAvailability()).toBe("insecure");
    await expect(enableBrowserPush(key)).rejects.toMatchObject({ code: "insecure" });
    expect(requestPermission).not.toHaveBeenCalled();
  });

  it("reports absent push support and cleans up without throwing", async () => {
    vi.stubGlobal("PushManager", undefined);
    expect(getPushAvailability()).toBe("unsupported");
    Reflect.deleteProperty(navigator, "serviceWorker");
    await expect(clearBrowserPush()).resolves.toBeUndefined();
  });
});
