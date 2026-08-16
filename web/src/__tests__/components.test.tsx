import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { ServiceControls } from "@/components/service-controls";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

// Test wrapper with providers
function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

describe("ServiceControls", () => {
  it("shows service status badge", async () => {
    render(<ServiceControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Running|Stopped/)).toBeInTheDocument();
    });
  });

  it("shows Stopped badge when status.running is false", async () => {
    server.use(
      http.get(`${API_BASE}/status`, () =>
        HttpResponse.json({
          running: false,
          initialized: true,
          config_summary: {},
        }),
      ),
    );

    render(<ServiceControls />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Stopped/)).toBeInTheDocument();
    });
  });
});
