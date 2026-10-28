/**
 * App-wide banner after a rollback (output-plugins plan D8).
 *
 * `GET /settings/restore-notice` reports that this build restored its own
 * pre-upgrade settings snapshot and moved the newer file aside. The banner
 * names that file (changes since the upgrade live only there), dismisses via
 * `DELETE /settings/restore-notice`, and renders nothing without a notice or
 * on the chrome-less routes (login, the FiestaPanel TV viewer).
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SettingsRestoredBanner } from "@/components/settings-restored-banner";

import { server } from "./mocks/server";

const API_BASE = "/api";
const ASIDE = "/app/data/settings.json.v4_aside-20261003T221500Z";

const NOTICE = {
  aside_path: ASIDE,
  aside_file: "settings.json.v4_aside-20261003T221500Z",
  found_version: 4,
  restored_version: 3,
  restored_at: "2026-10-03T22:15:00Z",
};

let pathname = "/";
vi.mock("@/hooks/use-router", () => ({
  usePathname: () => pathname,
}));

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

function serveNotice(notice: typeof NOTICE | null, onDelete?: () => Response) {
  const gets = { count: 0 };
  server.use(
    http.get(`${API_BASE}/settings/restore-notice`, () => {
      gets.count += 1;
      return HttpResponse.json({ notice });
    }),
    http.delete(`${API_BASE}/settings/restore-notice`, () => onDelete?.() ?? HttpResponse.json({ notice: null })),
  );
  return gets;
}

async function expectNoBanner() {
  await expect(
    waitFor(() => expect(screen.getByTestId("settings-restored-banner")).toBeInTheDocument(), { timeout: 300 }),
  ).rejects.toThrow();
}

describe("SettingsRestoredBanner", () => {
  beforeEach(() => {
    pathname = "/";
  });

  it("names the set-aside settings file", async () => {
    serveNotice(NOTICE);
    render(<SettingsRestoredBanner />, { wrapper: TestWrapper });

    const banner = await screen.findByTestId("settings-restored-banner");
    expect(banner).toHaveTextContent("Settings were restored from before the upgrade");
    expect(banner).toHaveTextContent(ASIDE);
  });

  it("renders nothing when there is no notice", async () => {
    serveNotice(null);
    const { container } = render(<SettingsRestoredBanner />, { wrapper: TestWrapper });

    await expectNoBanner();
    expect(container).toBeEmptyDOMElement();
  });

  it("dismissing calls the API and hides the banner", async () => {
    const user = userEvent.setup();
    let deleted = 0;
    serveNotice(NOTICE, () => {
      deleted += 1;
      return HttpResponse.json({ notice: null });
    });
    render(<SettingsRestoredBanner />, { wrapper: TestWrapper });

    await screen.findByTestId("settings-restored-banner");
    await user.click(screen.getByRole("button", { name: "Dismiss" }));

    await waitFor(() => expect(screen.queryByTestId("settings-restored-banner")).not.toBeInTheDocument());
    expect(deleted).toBe(1);
  });

  it("keeps the banner and says so when dismissing fails", async () => {
    const user = userEvent.setup();
    serveNotice(NOTICE, () => HttpResponse.json({ detail: "nope" }, { status: 500 }));
    render(<SettingsRestoredBanner />, { wrapper: TestWrapper });

    await screen.findByTestId("settings-restored-banner");
    await user.click(screen.getByRole("button", { name: "Dismiss" }));

    await waitFor(() =>
      expect(screen.getByTestId("settings-restored-banner")).toHaveTextContent("Could not dismiss. Try again."),
    );
  });

  it("stays off the FiestaPanel viewer and never asks the API there", async () => {
    pathname = "/panel/abc123";
    const gets = serveNotice(NOTICE);
    const { container } = render(<SettingsRestoredBanner />, { wrapper: TestWrapper });

    await expectNoBanner();
    expect(container).toBeEmptyDOMElement();
    expect(gets.count).toBe(0);
  });
});
