import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { ThemeProvider } from "@/hooks/use-theme";
import { describe, expect, it } from "vitest";

import { SystemControls } from "@/components/settings/system-controls";

import { server } from "./mocks/server";

const API_BASE = "/api";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="light">
        {children}
      </ThemeProvider>
    </QueryClientProvider>
  );
}

function withSidecar(available: boolean) {
  server.use(
    http.get(`${API_BASE}/system/update/status`, () => {
      return HttpResponse.json({
        updater_available: available,
        auto_update_enabled: false,
        auto_update_interval: "manual",
        profile: "docker",
        sidecar_url: "http://fiestaupdater:8765",
        last_check: null,
        last_update: null,
      });
    }),
  );
}

describe("SystemControls", () => {
  it("renders nothing when sidecar is unavailable", async () => {
    withSidecar(false);
    render(<SystemControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.queryByText("System")).not.toBeInTheDocument();
    });
  });

  it("renders System card when sidecar is available", async () => {
    withSidecar(true);
    render(<SystemControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("System")).toBeInTheDocument();
    });
    expect(screen.getByText("Restart")).toBeInTheDocument();
    expect(screen.getByText("Shutdown")).toBeInTheDocument();
  });

  it("shows update button labeled Re-pull Latest when up to date", async () => {
    withSidecar(true);
    render(<SystemControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Re-pull Latest")).toBeInTheDocument();
    });
  });

  it("shows Update Now button when update is available", async () => {
    withSidecar(true);
    server.use(
      http.get(`${API_BASE}/system/update-check`, () => {
        return HttpResponse.json({
          current_version: "2.0.1",
          latest_version: "2.0.2",
          update_available: true,
          package_url: "https://github.com/Fiestaboard/FiestaBoard/releases/latest",
          error: null,
          is_production: true,
        });
      }),
    );

    render(<SystemControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Update Now")).toBeInTheDocument();
    });
  });

  it("shows restart confirmation dialog on Restart click", async () => {
    withSidecar(true);
    render(<SystemControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Restart")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Restart"));

    await waitFor(() => {
      expect(screen.getByText("Restart FiestaBoard?")).toBeInTheDocument();
    });
  });

  it("shows shutdown confirmation dialog on Shutdown click", async () => {
    withSidecar(true);
    render(<SystemControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Shutdown")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Shutdown"));

    await waitFor(() => {
      expect(screen.getByText("Shut Down Host?")).toBeInTheDocument();
    });
  });

  it("cancels restart dialog without action", async () => {
    withSidecar(true);
    render(<SystemControls />, { wrapper: TestWrapper });

    await waitFor(() => screen.getByText("Restart"));
    fireEvent.click(screen.getByText("Restart"));
    await waitFor(() => screen.getByText("Restart FiestaBoard?"));

    fireEvent.click(screen.getByText("Cancel"));

    await waitFor(() => {
      expect(screen.queryByText("Restart FiestaBoard?")).not.toBeInTheDocument();
    });
  });
});
