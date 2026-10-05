/**
 * Settings → Hardware moved to Displays (plan D21): the tab is gone, and an
 * old `/settings?section=hardware` link lands on /displays.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SettingsPage from "../../app/routes/settings";
import { server } from "./mocks/server";

const search = { value: "" };

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), forward: vi.fn() }),
  useSearchParams: () => new URLSearchParams(search.value),
  usePathname: () => "/settings",
}));

vi.mock("@/components/wizard-provider", () => ({ useWizard: () => ({ triggerWizard: vi.fn() }) }));

function renderAt(query: string) {
  search.value = query;
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[`/settings?${query}`]}>
        <Routes>
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/displays" element={<div data-testid="displays-route" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  server.use(http.get("/api/network/wifi/capability", () => HttpResponse.json({ available: false })));
});

describe("Settings → Hardware", () => {
  it("an old ?section=hardware link lands on Displays", async () => {
    renderAt("section=hardware");
    expect(await screen.findByTestId("displays-route")).toBeInTheDocument();
  });

  it("is no longer a settings tab", async () => {
    renderAt("section=general");
    expect(await screen.findByRole("tab", { name: "General" })).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Hardware" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("displays-route")).not.toBeInTheDocument();
  });
});
