import "fake-indexeddb/auto";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HttpsRequiredBanner } from "@/components/pwa/https-required-banner";
import { formatLastConnected } from "@/components/pwa/last-known-board-card";
import { OfflineScreen } from "@/components/pwa/offline-screen";
import { clearLastKnownBoards } from "@/lib/pwa/last-known-board";

import OfflinePage from "../../app/routes/offline";
import { seedLastKnownBoard } from "./helpers/last-known-board";
import { server } from "./mocks/server";

const replace = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-router", () => ({ useRouter: () => ({ replace, push: vi.fn() }) }));

function withClient(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

function setOnline(value: boolean) {
  vi.spyOn(window.navigator, "onLine", "get").mockReturnValue(value);
}

beforeEach(async () => {
  await clearLastKnownBoards();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("OfflineScreen (WEB-16 split)", () => {
  it("says this device is offline and that the hub and displays are fine", () => {
    render(<OfflineScreen kind="device-offline" onRetry={() => {}} />);
    expect(screen.getByRole("heading", { level: 1, name: "You’re offline" })).toBeInTheDocument();
    expect(screen.getByText(/isn’t connected to a network/)).toHaveTextContent(/hub and displays are fine/);
    expect(screen.queryByRole("link", { name: /connection help/i })).not.toBeInTheDocument();
  });

  it("says the hub didn't answer, with the checks and Connection help, when this device is online", () => {
    render(<OfflineScreen kind="hub-unreachable" onRetry={() => {}} />);
    expect(screen.getByRole("heading", { level: 1, name: "Can’t reach your hub" })).toBeInTheDocument();
    expect(screen.getByText(/didn’t answer/)).toHaveTextContent(window.location.host);
    expect(screen.getByText(/plugged in/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /connection help/i })).toHaveAttribute(
      "href",
      expect.stringContaining("troubleshooting"),
    );
  });

  it("Try again calls back", () => {
    const onRetry = vi.fn();
    render(<OfflineScreen kind="hub-unreachable" onRetry={onRetry} />);
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("shows the last frame this device saw, labelled as possibly out of date", async () => {
    await seedLastKnownBoard({
      boardId: "b1",
      owner: "maya",
      message: "OPEN MIC TONIGHT",
      rows: 6,
      cols: 22,
      board: { name: "Lobby wall", device_type: "flagship", board_color: "black" },
      savedAt: Date.now(),
    });
    render(withClient(<OfflineScreen kind="device-offline" onRetry={() => {}} />));
    const card = await screen.findByTestId("last-known-board");
    expect(card).toHaveTextContent("Last known · Lobby wall");
    expect(card).toHaveTextContent(/Last connected .* may be out of date/);
  });

  it("hides an already displayed frame when another tab signs out", async () => {
    await seedLastKnownBoard({
      boardId: "b1",
      owner: "maya",
      message: "PRIVATE",
      rows: 6,
      cols: 22,
      board: null,
      savedAt: 1,
    });
    render(withClient(<OfflineScreen kind="device-offline" onRetry={() => {}} />));
    await screen.findByTestId("last-known-board");
    await act(async () => {
      await clearLastKnownBoards();
      window.dispatchEvent(
        new StorageEvent("storage", { key: "fiestaboard-offline-revoked:", newValue: "signed-out" }),
      );
    });
    expect(screen.queryByTestId("last-known-board")).not.toBeInTheDocument();
  });

  it("shows no last-known card when nothing was recorded", async () => {
    render(<OfflineScreen kind="device-offline" onRetry={() => {}} />);
    await act(async () => {
      await new Promise((r) => setTimeout(r, 30));
    });
    expect(screen.queryByTestId("last-known-board")).not.toBeInTheDocument();
  });
});

describe("formatLastConnected", () => {
  it("shows the time alone today and the date on another day", () => {
    const now = new Date(2026, 10, 13, 18, 0).getTime();
    expect(formatLastConnected(new Date(2026, 10, 13, 14, 14).getTime(), now, "en-US")).toBe("2:14 PM");
    expect(formatLastConnected(new Date(2026, 10, 12, 14, 14).getTime(), now, "en-US")).toBe("Nov 12, 2:14 PM");
  });
});

describe("/offline route", () => {
  function renderRoute() {
    replace.mockReset();
    render(withClient(<OfflinePage />));
  }

  it("is You're offline when the device has no network", () => {
    setOnline(false);
    renderRoute();
    expect(screen.getByRole("heading", { name: "You’re offline" })).toBeInTheDocument();
  });

  it("is Can't reach your hub when online but the hub doesn't answer", async () => {
    setOnline(true);
    server.use(http.get("*/api/health", () => HttpResponse.error()));
    renderRoute();
    expect(await screen.findByRole("heading", { name: "Can’t reach your hub" })).toBeInTheDocument();
  });

  it("goes back to Home once the hub answers", async () => {
    setOnline(true);
    server.use(http.get("*/api/health", () => HttpResponse.json({ status: "ok" })));
    renderRoute();
    await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
  });
});

describe("HttpsRequiredBanner", () => {
  it("says install and offline need a secure address, with the fix, on plain http", () => {
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: false });
    render(<HttpsRequiredBanner />);
    expect(screen.getByText("Requires HTTPS")).toBeInTheDocument();
    expect(screen.getByText(/Install and offline need a secure address/)).toHaveTextContent(
      `http://${window.location.host}`,
    );
    expect(screen.getByRole("link", { name: /how to set up https/i })).toBeInTheDocument();
  });

  it("renders nothing on a secure origin", () => {
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
    const { container } = render(<HttpsRequiredBanner />);
    expect(container).toBeEmptyDOMElement();
  });
});
