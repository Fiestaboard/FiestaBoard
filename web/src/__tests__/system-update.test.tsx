import { describe, it, expect } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";
import { SystemUpdate } from "@/components/settings/system-update";

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
  it("always shows Restart Only and Pull & Restart buttons when up to date in production", async () => {
    server.use(
      http.get(`${API_BASE}/system/update-check`, () => {
        return HttpResponse.json({
          current_version: "2.0.1",
          latest_version: "2.0.1",
          update_available: false,
          package_url: "https://github.com/Fiestaboard/FiestaBoard/pkgs/container/fiestaboard",
          error: null,
          is_production: true,
        });
      })
    );

    render(<SystemUpdate />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Up to Date")).toBeInTheDocument();
    });

    // All buttons should be visible
    expect(screen.getByText("Restart Only")).toBeInTheDocument();
    expect(screen.getByText("View Package")).toBeInTheDocument();

    // Pull & Restart should be disabled (no update available)
    const pullButton = screen.getByRole("button", { name: /Pull & Restart/i });
    expect(pullButton).toBeDisabled();

    // Restart Only should be enabled (production mode)
    const restartButton = screen.getByRole("button", { name: /Restart Only/i });
    expect(restartButton).toBeEnabled();
  });

  it("shows all buttons disabled in non-production mode", async () => {
    server.use(
      http.get(`${API_BASE}/system/update-check`, () => {
        return HttpResponse.json({
          current_version: "2.0.1",
          latest_version: "2.0.2",
          update_available: true,
          package_url: "https://github.com/Fiestaboard/FiestaBoard/pkgs/container/fiestaboard",
          error: null,
          is_production: false,
        });
      })
    );

    render(<SystemUpdate />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Update Available")).toBeInTheDocument();
    });

    // All buttons should be visible
    expect(screen.getByText("Restart Only")).toBeInTheDocument();
    expect(screen.getByText("View Package")).toBeInTheDocument();

    // Both action buttons should be disabled (non-production)
    const pullButton = screen.getByRole("button", { name: /Pull & Restart/i });
    expect(pullButton).toBeDisabled();

    const restartButton = screen.getByRole("button", { name: /Restart Only/i });
    expect(restartButton).toBeDisabled();

    // Should show non-production message
    expect(
      screen.getByText("Container management is only available in production mode.")
    ).toBeInTheDocument();
  });

  it("enables all action buttons when update available in production", async () => {
    server.use(
      http.get(`${API_BASE}/system/update-check`, () => {
        return HttpResponse.json({
          current_version: "2.0.1",
          latest_version: "2.0.2",
          update_available: true,
          package_url: "https://github.com/Fiestaboard/FiestaBoard/pkgs/container/fiestaboard",
          error: null,
          is_production: true,
        });
      })
    );

    render(<SystemUpdate />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Update Available")).toBeInTheDocument();
    });

    // Both action buttons should be enabled
    const pullButton = screen.getByRole("button", { name: /Pull & Restart/i });
    expect(pullButton).toBeEnabled();

    const restartButton = screen.getByRole("button", { name: /Restart Only/i });
    expect(restartButton).toBeEnabled();
  });

  it("shows buttons when no update available in non-production mode", async () => {
    server.use(
      http.get(`${API_BASE}/system/update-check`, () => {
        return HttpResponse.json({
          current_version: "2.0.1",
          latest_version: "2.0.1",
          update_available: false,
          package_url: "https://github.com/Fiestaboard/FiestaBoard/pkgs/container/fiestaboard",
          error: null,
          is_production: false,
        });
      })
    );

    render(<SystemUpdate />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Up to Date")).toBeInTheDocument();
    });

    // All buttons should be visible but disabled
    const pullButton = screen.getByRole("button", { name: /Pull & Restart/i });
    expect(pullButton).toBeDisabled();

    const restartButton = screen.getByRole("button", { name: /Restart Only/i });
    expect(restartButton).toBeDisabled();

    // Non-production message
    expect(
      screen.getByText("Container management is only available in production mode.")
    ).toBeInTheDocument();
  });
});
