import { pushApi } from "@/lib/api/push";
import { appUrl } from "@/lib/base-path";

import { isSecureOrigin, isStandalone } from "./environment";
import { registerServiceWorker } from "./register-service-worker";

export type PushAvailability = "supported" | "insecure" | "embedded" | "install" | "unsupported";

export class BrowserPushError extends Error {
  constructor(public readonly code: PushAvailability | NotificationPermission | "worker" | "unsubscribe") {
    super(code);
    this.name = "BrowserPushError";
  }
}

export function getPushAvailability(): PushAvailability {
  if (!isSecureOrigin()) return "insecure";
  // HA ingress is often an iframe. Browsers cannot request notification
  // permission there; HTTPS on the outer Home Assistant page does not fix it.
  if (window.top !== window.self) return "embedded";
  const { userAgent, maxTouchPoints } = navigator;
  const ios = /iPhone|iPad|iPod/.test(userAgent) || (/Macintosh/.test(userAgent) && maxTouchPoints > 1);
  if (ios && !isStandalone()) return "install";
  if (!navigator.serviceWorker || typeof Notification === "undefined" || typeof PushManager === "undefined") {
    return "unsupported";
  }
  return "supported";
}

/** Never use a parent/other app's worker, particularly on a shared HA origin. */
async function appRegistration(): Promise<ServiceWorkerRegistration | undefined> {
  if (!navigator.serviceWorker) return undefined;
  const registration = await navigator.serviceWorker.getRegistration(appUrl("/"));
  return registration?.scope === new URL(appUrl("/"), location.href).href ? registration : undefined;
}

export async function readBrowserPush(): Promise<{ permission: NotificationPermission; subscribed: boolean }> {
  const permission = typeof Notification === "undefined" ? "default" : Notification.permission;
  try {
    const registration = await appRegistration();
    const subscription = await registration?.pushManager?.getSubscription();
    return {
      permission,
      subscribed: !!subscription && (!subscription.expirationTime || subscription.expirationTime > Date.now()),
    };
  } catch {
    return { permission, subscribed: false };
  }
}

async function activeRegistration(): Promise<ServiceWorkerRegistration> {
  const registration = (await appRegistration()) ?? (await registerServiceWorker());
  if (!registration?.pushManager) throw new BrowserPushError("worker");
  if (registration.active) return registration;
  const worker = registration.installing ?? registration.waiting;
  if (!worker) throw new BrowserPushError("worker");
  await new Promise<void>((resolve, reject) => {
    const finish = () => {
      if (worker.state !== "activated" && worker.state !== "redundant") return;
      clearTimeout(timer);
      worker.removeEventListener("statechange", finish);
      if (worker.state === "activated") resolve();
      else reject(new BrowserPushError("worker"));
    };
    const timer = setTimeout(() => {
      worker.removeEventListener("statechange", finish);
      reject(new BrowserPushError("worker"));
    }, 10_000);
    worker.addEventListener("statechange", finish);
    finish();
  });
  return registration;
}

export async function enableBrowserPush(publicKey: string) {
  const availability = getPushAvailability();
  if (availability !== "supported") throw new BrowserPushError(availability);
  // Keep the permission request in the activation stack: no network or SW await first.
  const permission =
    Notification.permission === "default" ? await Notification.requestPermission() : Notification.permission;
  if (permission !== "granted") throw new BrowserPushError(permission);
  const key = Uint8Array.from(atob(publicKey.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
  const registration = await activeRegistration();
  let subscription = await registration.pushManager.getSubscription();
  const oldKey = subscription?.options.applicationServerKey;
  const matches =
    oldKey && oldKey.byteLength === key.byteLength && new Uint8Array(oldKey).every((v, i) => v === key[i]);
  if (
    subscription &&
    (!matches || (subscription.expirationTime !== null && subscription.expirationTime <= Date.now()))
  ) {
    if (!(await subscription.unsubscribe())) throw new BrowserPushError("unsubscribe");
    subscription = null;
  }
  const created = !subscription;
  subscription ??= await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key });
  try {
    return await pushApi.subscribe(subscription.toJSON());
  } catch (error) {
    if (created) await subscription.unsubscribe().catch(() => false);
    throw error;
  }
}

/** Post-logout server sessions are already invalid; clean browser state best-effort. */
export async function clearBrowserPush(): Promise<void> {
  try {
    const registration = await appRegistration();
    if (!registration) return;
    // Notify first so a failed/wedged browser unsubscribe cannot preserve alerts.
    registration.active?.postMessage({ type: "CLEAR_PUSH" });
    const notifications = await registration.getNotifications?.();
    notifications?.forEach((notification) => notification.close());
    const subscription = await registration.pushManager?.getSubscription();
    await subscription?.unsubscribe();
  } catch {
    /* Browser cleanup must never strand a signed-out user. */
  }
}

export async function disableBrowserPush() {
  try {
    return await pushApi.unsubscribe();
  } finally {
    await clearBrowserPush();
  }
}
