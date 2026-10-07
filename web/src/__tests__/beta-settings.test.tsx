/**
 * Settings → Beta after HTTPS (Beta) was removed (settings v5): the card
 * offers the transition-plugin and output-plugin switches and nothing that
 * serves the UI over HTTPS or asks for a restart.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { BetaSettings } from "@/components/settings/beta-settings";

import { server } from "./mocks/server";

const API_BASE = "/api";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("BetaSettings", () => {
  it("offers the transition and output plugin switches", async () => {
    render(<BetaSettings />, { wrapper: TestWrapper });

    expect(await screen.findByRole("switch", { name: "Transition Plugins" })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Output Plugins" })).toBeInTheDocument();
  });

  it("has no HTTPS switch", async () => {
    render(<BetaSettings />, { wrapper: TestWrapper });

    await screen.findByRole("switch", { name: "Transition Plugins" });
    expect(screen.queryByRole("switch", { name: /https/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/self-signed/i)).not.toBeInTheDocument();
    expect(screen.getAllByRole("switch")).toHaveLength(2);
  });

  it("saves a flag without asking for a restart", async () => {
    const user = userEvent.setup();
    let body: unknown = null;
    server.use(
      http.put(`${API_BASE}/settings/beta`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({
          settings: { transition_plugins_enabled: true, output_plugins_enabled: false },
        });
      }),
    );
    render(<BetaSettings />, { wrapper: TestWrapper });

    await user.click(await screen.findByRole("switch", { name: "Transition Plugins" }));

    await waitFor(() => expect(body).toEqual({ transition_plugins_enabled: true }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
