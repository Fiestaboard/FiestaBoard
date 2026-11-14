import { describe, expect, it, vi } from "vitest";

import { registerServiceWorker } from "@/lib/pwa/register-service-worker";

describe("registerServiceWorker", () => {
  it("registers sw.js at the app's base, never bypassing the HTTP cache rules, on a secure origin", async () => {
    const register = vi.fn().mockResolvedValue({ scope: "/" });
    const reg = await registerServiceWorker({
      isSecureContext: true,
      navigator: { serviceWorker: { register } as unknown as ServiceWorkerContainer },
    });
    expect(register).toHaveBeenCalledWith("/sw.js", { scope: "/", updateViaCache: "none" });
    expect(reg).toEqual({ scope: "/" });
  });

  it("registers nothing on plain http", async () => {
    const register = vi.fn();
    expect(
      await registerServiceWorker({
        isSecureContext: false,
        navigator: { serviceWorker: { register } as unknown as ServiceWorkerContainer },
      }),
    ).toBeNull();
    expect(register).not.toHaveBeenCalled();
  });

  it("does nothing where the browser has no service workers", async () => {
    expect(await registerServiceWorker({ isSecureContext: true, navigator: {} })).toBeNull();
  });

  it("leaves the app working when registration fails", async () => {
    const register = vi.fn().mockRejectedValue(new Error("SecurityError"));
    expect(
      await registerServiceWorker({
        isSecureContext: true,
        navigator: { serviceWorker: { register } as unknown as ServiceWorkerContainer },
      }),
    ).toBeNull();
  });
});
