import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { SystemUpdate } from "@/components/settings/system-update";
import { ThemeProvider } from "@/hooks/use-theme";

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

describe("SystemUpdate", () => {
  it("renders nothing when up to date", async () => {
    server.use(
      http.get(`${API_BASE}/system/update-check`, () => {
        return HttpResponse.json({
          current_version: "2.0.1",
          latest_version: "2.0.1",
          update_available: false,
          package_url: "https://github.com/Fiestaboard/FiestaBoard/releases/latest",
          error: null,
          is_production: true,
        });
      }),
    );

    render(<SystemUpdate />, { wrapper: TestWrapper });

    // Wait for query to settle, then verify no alert is rendered
    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
    expect(screen.queryByText("Update Available")).not.toBeInTheDocument();
  });

  it("shows update alert when update is available", async () => {
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

    render(<SystemUpdate />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Update Available")).toBeInTheDocument();
    });

    // Should show version badge and current version
    expect(screen.getByText("v2.0.2")).toBeInTheDocument();
    expect(screen.getByText("You are running v2.0.1.")).toBeInTheDocument();

    // Should show View Release link but no restart/upgrade buttons
    expect(screen.getByText("View Release")).toBeInTheDocument();
    expect(screen.queryByText("Restart Only")).not.toBeInTheDocument();
    expect(screen.queryByText(/Pull & Restart/i)).not.toBeInTheDocument();
  });

  it("renders nothing when update check fails", async () => {
    server.use(
      http.get(`${API_BASE}/system/update-check`, () => {
        return HttpResponse.error();
      }),
    );

    render(<SystemUpdate />, { wrapper: TestWrapper });

    // Wait for query to settle, then verify no alert is rendered
    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
    expect(screen.queryByText("Update Available")).not.toBeInTheDocument();
  });

  it("renders nothing in non-production mode with no update", async () => {
    server.use(
      http.get(`${API_BASE}/system/update-check`, () => {
        return HttpResponse.json({
          current_version: "2.0.1",
          latest_version: "2.0.1",
          update_available: false,
          package_url: "https://github.com/Fiestaboard/FiestaBoard/releases/latest",
          error: null,
          is_production: false,
        });
      }),
    );

    render(<SystemUpdate />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
    expect(screen.queryByText("Update Available")).not.toBeInTheDocument();
  });
});
