import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import { SilenceModeStatus, SilenceModeStatusCompact } from "@/components/silence-mode-status";

import { server } from "./mocks/server";

const API_BASE = "/api";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("SilenceModeStatus branch coverage", () => {
  beforeEach(() => {
    // Reset to default handlers - general config with timezone
    server.use(
      http.get(`${API_BASE}/config/general`, () =>
        HttpResponse.json({
          timezone: "America/Los_Angeles",
          refresh_interval_seconds: 300,
          output_target: "board",
        }),
      ),
    );
  });

  it("uses fallback timezone when generalConfig.timezone is missing", async () => {
    server.use(
      http.get(`${API_BASE}/config/general`, () =>
        HttpResponse.json({
          refresh_interval_seconds: 300,
          output_target: "board",
          // timezone omitted - should fallback to America/Los_Angeles
        }),
      ),
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json({
          enabled: true,
          active: true,
          start_time_utc: "04:00+00:00",
          end_time_utc: "15:00+00:00",
          current_time_utc: "2025-12-26T18:30:00+00:00",
          next_change_utc: "2025-12-27T04:00:00+00:00",
        }),
      ),
    );

    render(<SilenceModeStatus showDetails={true} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Silence Mode: Active/i)).toBeInTheDocument();
    });
    // Details paragraph with timezone abbreviation
    expect(screen.getByText(/Until/i)).toBeInTheDocument();
  });

  it("shows active badge with details when showDetails is true", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json({
          enabled: true,
          active: true,
          start_time_utc: "04:00+00:00",
          end_time_utc: "15:00+00:00",
          current_time_utc: "2025-12-26T18:30:00+00:00",
          next_change_utc: "2025-12-27T04:00:00+00:00",
        }),
      ),
    );

    render(<SilenceModeStatus showDetails={true} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Silence Mode: Active/i)).toBeInTheDocument();
      expect(screen.getByText(/Until/i)).toBeInTheDocument();
    });
  });

  it("shows active badge without details when showDetails is false", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json({
          enabled: true,
          active: true,
          start_time_utc: "04:00+00:00",
          end_time_utc: "15:00+00:00",
          current_time_utc: "2025-12-26T18:30:00+00:00",
          next_change_utc: "2025-12-27T04:00:00+00:00",
        }),
      ),
    );

    render(<SilenceModeStatus showDetails={false} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Silence Mode: Active/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Until/i)).not.toBeInTheDocument();
  });

  it("shows inactive badge with details when showDetails is true", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json({
          enabled: true,
          active: false,
          start_time_utc: "04:00+00:00",
          end_time_utc: "15:00+00:00",
          current_time_utc: "2025-12-26T18:30:00+00:00",
          next_change_utc: "2025-12-27T04:00:00+00:00",
        }),
      ),
    );

    render(<SilenceModeStatus showDetails={true} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Silence Mode: Inactive/i)).toBeInTheDocument();
      expect(screen.getByText(/Starts at/i)).toBeInTheDocument();
    });
  });

  it("shows inactive badge without details when showDetails is false", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json({
          enabled: true,
          active: false,
          start_time_utc: "04:00+00:00",
          end_time_utc: "15:00+00:00",
          current_time_utc: "2025-12-26T18:30:00+00:00",
          next_change_utc: "2025-12-27T04:00:00+00:00",
        }),
      ),
    );

    render(<SilenceModeStatus showDetails={false} />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Silence Mode: Inactive/i)).toBeInTheDocument();
    });
    expect(screen.queryByText(/Starts at/i)).not.toBeInTheDocument();
  });
});

describe("SilenceModeStatusCompact branch coverage", () => {
  it("returns null when silence mode is disabled", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json({
          enabled: false,
          active: false,
          start_time_utc: "04:00+00:00",
          end_time_utc: "15:00+00:00",
          current_time_utc: "2025-12-26T18:30:00+00:00",
          next_change_utc: "2025-12-27T04:00:00+00:00",
        }),
      ),
    );

    const { container } = render(<SilenceModeStatusCompact />, { wrapper: TestWrapper });

    await waitFor(() => {
      // When disabled, returns null - no Badge rendered
      expect(container.querySelector('[class*="badge"]')).toBeNull();
    });
  });

  it("shows destructive badge with Silent when active", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json({
          enabled: true,
          active: true,
          start_time_utc: "04:00+00:00",
          end_time_utc: "15:00+00:00",
          current_time_utc: "2025-12-26T18:30:00+00:00",
          next_change_utc: "2025-12-27T04:00:00+00:00",
        }),
      ),
    );

    render(<SilenceModeStatusCompact />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Silent/i)).toBeInTheDocument();
    });
  });

  it("shows secondary badge with Active when inactive", async () => {
    server.use(
      http.get(`${API_BASE}/silence-status`, () =>
        HttpResponse.json({
          enabled: true,
          active: false,
          start_time_utc: "04:00+00:00",
          end_time_utc: "15:00+00:00",
          current_time_utc: "2025-12-26T18:30:00+00:00",
          next_change_utc: "2025-12-27T04:00:00+00:00",
        }),
      ),
    );

    render(<SilenceModeStatusCompact />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/^Active$/)).toBeInTheDocument();
    });
  });
});
