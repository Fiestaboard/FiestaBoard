import { seedLastKnownBoard } from "./helpers/last-known-board";
import "fake-indexeddb/auto";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { BootGate } from "@/components/boot-gate";
import { PwaLifecycle } from "@/components/pwa/pwa-lifecycle";
import { readLastKnownBoard } from "@/lib/pwa/last-known-board";

import { server } from "./mocks/server";

const route = vi.hoisted(() => ({ pathname: "/" }));
vi.mock("@/hooks/use-router", () => ({ usePathname: () => route.pathname }));

function withClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("BootGate offline branch (WEB-16)", () => {
  it("says You're offline at once, instead of Waiting to start, when the device has no network", () => {
    vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(false);
    server.use(http.get("*/api/health", () => HttpResponse.error()));
    render(withClient(<BootGate>app</BootGate>));
    expect(screen.getByRole("heading", { level: 1, name: "You’re offline" })).toBeInTheDocument();
    expect(screen.queryByText("app")).not.toBeInTheDocument();
  });

  it("shows hub-unreachable after the cold-boot timeout while the device is online", async () => {
    vi.useFakeTimers();
    try {
      vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(true);
      server.use(http.get("*/api/health", () => HttpResponse.error()));
      render(withClient(<BootGate>app</BootGate>));
      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_001);
      });
      expect(screen.getByRole("heading", { level: 1, name: "Can’t reach your hub" })).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });

  it("lets the app through when the device is online and the hub answers", async () => {
    vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(true);
    server.use(http.get("*/api/health", () => HttpResponse.json({ status: "ok" })));
    render(withClient(<BootGate>app</BootGate>));
    expect(await screen.findByText("app")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "You’re offline" })).not.toBeInTheDocument();
  });
});

describe("PwaLifecycle", () => {
  function mount(path: string) {
    route.pathname = path;
    return render(withClient(<PwaLifecycle />));
  }
  const rec = { boardId: "b1", owner: "maya", message: "HI", rows: 6, cols: 22, board: null, savedAt: 1 };

  it("wipes the last-known board on the sign-in page", async () => {
    await seedLastKnownBoard(rec);
    mount("/login");
    await vi.waitFor(async () => expect(await readLastKnownBoard()).toBeNull());
  });

  it("keeps it on any other page", async () => {
    await seedLastKnownBoard(rec);
    mount("/pages");
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(await readLastKnownBoard()).not.toBeNull();
  });
});
