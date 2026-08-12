/**
 * Transition-plugin picker inside the global Board Transitions settings card.
 *
 * The backend accepts `"plugin:<id>"` anywhere a built-in Vestaboard local-API
 * strategy is accepted, but the card historically only offered the 7 built-ins.
 * These tests pin the beta-gated plugin group: it appears only when
 * `beta.transition_plugins_enabled` is on, selecting a plugin saves
 * `plugin:<id>`, the local-API-only advanced knobs disappear (they are
 * meaningless for plugin transitions), and an already-saved plugin strategy is
 * never silently dropped when the plugin is unavailable.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TransitionSettings } from "@/components/settings/transition-settings";
import { ThemeProvider } from "@/hooks/use-theme";

import { mockTransitionSettings } from "./mocks/handlers";
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

/** Override /settings/all so the card loads with a specific saved strategy. */
function useStrategy(strategy: string | null) {
  server.use(
    http.get(`${API_BASE}/settings/all`, () => {
      return HttpResponse.json({
        general: { timezone: "America/Los_Angeles" },
        silence_schedule: {},
        polling: { interval_seconds: 300 },
        transitions: { ...mockTransitionSettings, strategy },
        output: { target: "board", effective_target: "board", available_targets: [] },
        board: {
          board_type: "black",
          boards: [{ id: "default", name: "Flagship", device_type: "flagship", board_color: "black" }],
          devices: ["flagship"],
        },
        mqtt: {
          enabled: false,
          broker_host: "localhost",
          broker_port: 1883,
          username: "",
          password: "",
          external_url: "",
        },
        status: { running: true, config_summary: {} },
      });
    }),
  );
}

function useBeta(enabled: boolean) {
  server.use(
    http.get(`${API_BASE}/settings/beta`, () => {
      return HttpResponse.json({
        settings: { https_enabled: false, transition_plugins_enabled: enabled },
        https: { cert_present: false, cert_path: "", key_path: "", updater_available: false },
      });
    }),
  );
}

function pluginEntry(id: string, name: string, description: string) {
  return {
    id,
    name,
    description,
    icon: "Sparkles",
    version: "1.0.0",
    author: "Test",
    settings_schema: {},
    transition_settings: {
      interruptible: true,
      min_interval_ms: 0,
      max_frames: 100,
      max_runtime_seconds: 30,
    },
    config: {},
    strategy: `plugin:${id}`,
  };
}

function usePlugins(...entries: ReturnType<typeof pluginEntry>[]) {
  let called = 0;
  server.use(
    http.get(`${API_BASE}/transitions/plugins`, () => {
      called += 1;
      return HttpResponse.json({ plugins: entries });
    }),
  );
  return () => called;
}

describe("TransitionSettings transition plugins", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders installed transition plugins as options when the beta is enabled", async () => {
    useBeta(true);
    usePlugins(pluginEntry("typewriter", "Typewriter", "Types the new message one character at a time."));

    render(<TransitionSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Board Transitions")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Typewriter" })).toBeInTheDocument();
    });
  });

  it("saves strategy as plugin:<id> when a plugin option is clicked", async () => {
    useBeta(true);
    usePlugins(pluginEntry("slot_machine", "Slot Machine", "Spins each column into place."));

    let updatePayload: Record<string, unknown> | undefined;
    server.use(
      http.put(`${API_BASE}/settings/transitions`, async ({ request }) => {
        updatePayload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          status: "success",
          settings: { strategy: "plugin:slot_machine", step_interval_ms: 500, step_size: 2 },
        });
      }),
    );

    render(<TransitionSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Slot Machine" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Slot Machine" }));

    await waitFor(
      () => {
        expect(updatePayload).toBeDefined();
      },
      { timeout: 3000 },
    );

    expect(updatePayload?.strategy).toBe("plugin:slot_machine");
  });

  it("does not render or fetch plugin options when the beta is disabled", async () => {
    useBeta(false);
    const pluginFetches = usePlugins(pluginEntry("typewriter", "Typewriter", "Types one character at a time."));

    render(<TransitionSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Board Transitions")).toBeInTheDocument();
    });

    // Built-ins still render exactly as before.
    expect(screen.getByRole("button", { name: "Random" })).toBeInTheDocument();

    expect(screen.queryByRole("button", { name: "Typewriter" })).not.toBeInTheDocument();
    expect(pluginFetches()).toBe(0);
  });

  it("hides the local-API advanced options while a plugin strategy is selected", async () => {
    useBeta(true);
    usePlugins(pluginEntry("typewriter", "Typewriter", "Types one character at a time."));
    useStrategy("plugin:typewriter");

    render(<TransitionSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Typewriter" })).toBeInTheDocument();
    });

    expect(screen.queryByText("Advanced Options")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Step Interval (ms)")).not.toBeInTheDocument();
  });

  it("notes that plugin transitions work on any board connection when one is selected", async () => {
    useBeta(true);
    usePlugins(pluginEntry("typewriter", "Typewriter", "Types one character at a time."));
    useStrategy("plugin:typewriter");

    render(<TransitionSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Typewriter" })).toBeInTheDocument();
    });

    expect(screen.getByText(/any board connection/i)).toBeInTheDocument();
  });

  it("shows a chip for a saved plugin strategy that is no longer available", async () => {
    // Beta off, but the user previously saved a plugin strategy: it must stay
    // visible and selectable-away-from rather than silently vanishing.
    useBeta(false);
    useStrategy("plugin:quiet_library");

    render(<TransitionSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Board Transitions")).toBeInTheDocument();
    });

    expect(screen.getByRole("button", { name: "quiet_library" })).toBeInTheDocument();
  });

  it("keeps built-in strategy saves unchanged when the beta is enabled", async () => {
    useBeta(true);
    usePlugins(pluginEntry("typewriter", "Typewriter", "Types one character at a time."));

    let updatePayload: Record<string, unknown> | undefined;
    server.use(
      http.put(`${API_BASE}/settings/transitions`, async ({ request }) => {
        updatePayload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          status: "success",
          settings: { strategy: "random", step_interval_ms: 500, step_size: 2 },
        });
      }),
    );

    render(<TransitionSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Random" })).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Random" }));

    await waitFor(
      () => {
        expect(updatePayload).toBeDefined();
      },
      { timeout: 3000 },
    );

    expect(updatePayload?.strategy).toBe("random");
  });
});
