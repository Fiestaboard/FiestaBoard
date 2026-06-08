import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "./mocks/server";

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/settings",
}));

import { MqttSettingsCard } from "@/components/settings/mqtt-settings";

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

describe("MqttSettingsCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders the MQTT settings card with title", async () => {
    render(<MqttSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Home Assistant (MQTT)")).toBeInTheDocument();
    });
  });

  it("shows the enable/disable toggle", async () => {
    render(<MqttSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("switch")).toBeInTheDocument();
    });
  });

  it("shows description text", async () => {
    render(<MqttSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText(/Expose FiestaBoard as a device in Home Assistant/)).toBeInTheDocument();
    });
  });

  it("shows broker configuration section", async () => {
    render(<MqttSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Broker configuration")).toBeInTheDocument();
    });
  });

  it("shows Connected badge when MQTT is enabled and connected", async () => {
    server.use(
      http.get(`${API_BASE}/settings/mqtt`, () =>
        HttpResponse.json({
          enabled: true,
          broker_host: "192.168.1.10",
          broker_port: 1883,
          username: "ha_user",
          password: "***",
          external_url: "http://192.168.1.50:4420",
        }),
      ),
      http.get(`${API_BASE}/mqtt/status`, () =>
        HttpResponse.json({
          enabled: true,
          connected: true,
          running: true,
        }),
      ),
    );

    render(<MqttSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Connected")).toBeInTheDocument();
    });
  });

  it("shows Disconnected badge when MQTT is enabled but not connected", async () => {
    server.use(
      http.get(`${API_BASE}/settings/mqtt`, () =>
        HttpResponse.json({
          enabled: true,
          broker_host: "192.168.1.10",
          broker_port: 1883,
          username: "",
          password: "",
          external_url: "",
        }),
      ),
      http.get(`${API_BASE}/mqtt/status`, () =>
        HttpResponse.json({
          enabled: true,
          connected: false,
          running: true,
        }),
      ),
    );

    render(<MqttSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Disconnected")).toBeInTheDocument();
    });
  });

  it("does not show connection badge when MQTT is disabled", async () => {
    render(<MqttSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Home Assistant (MQTT)")).toBeInTheDocument();
    });

    expect(screen.queryByText("Connected")).not.toBeInTheDocument();
    expect(screen.queryByText("Disconnected")).not.toBeInTheDocument();
  });
});
