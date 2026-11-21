import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Home from "../../app/routes/home";
import { server } from "./mocks/server";

const triggerWizard = vi.fn();
vi.mock("@/components/wizard-provider", () => ({ useWizard: () => ({ triggerWizard }) }));
vi.mock("@/hooks/use-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/components/active-page-display", () => ({ ActivePageDisplay: () => <section aria-label="Active board" /> }));
vi.mock("@/components/home/home-compose", () => ({ HomeCompose: () => null }));
vi.mock("@/components/status-banners/status-banner-host", () => ({ StatusBannerHost: () => null }));

function renderHome(placeholder = false) {
  server.use(
    http.get("/api/settings/board", () =>
      HttpResponse.json({
        boards: placeholder
          ? [{ id: "default", name: "My Board", device_type: "flagship", output: "vestaboard", output_config: {} }]
          : [],
      }),
    ),
    http.get("/api/config/validate", () =>
      HttpResponse.json({ valid: false, is_first_run: false, errors: [], missing_fields: [] }),
    ),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Home />
    </QueryClientProvider>,
  );
}

beforeEach(() => triggerWizard.mockClear());

describe("Home without displays", () => {
  it("replaces the active board with a useful empty state after setup is skipped", async () => {
    renderHome();
    expect(await screen.findByRole("region", { name: "No displays yet" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Active board" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add display" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run setup again" })).toBeInTheDocument();
  });
  it("treats an untouched seed placeholder as no display", async () => {
    renderHome(true);
    expect(await screen.findByRole("region", { name: "No displays yet" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Active board" })).not.toBeInTheDocument();
  });
  it("opens the two-step Add display dialog without opening the wizard", async () => {
    renderHome();
    await userEvent.click(await screen.findByRole("button", { name: "Add display" }));
    expect(await screen.findByRole("dialog", { name: "Add a display" })).toBeInTheDocument();
    expect(screen.getByText("Step 1 of 2 · What do you want FiestaBoard to show on?")).toBeInTheDocument();
    expect(triggerWizard).not.toHaveBeenCalled();
  });
  it("opens the wizard only from Run setup again", async () => {
    renderHome();
    await userEvent.click(await screen.findByRole("button", { name: "Run setup again" }));
    await waitFor(() => expect(triggerWizard).toHaveBeenCalledOnce());
  });
});
