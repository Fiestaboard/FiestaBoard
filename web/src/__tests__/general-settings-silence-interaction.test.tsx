// Tests that exercise silence-schedule interaction handlers in GeneralSettings:
// - TimePicker onChange (handleSilenceTimeChange start + end branches)
// - mode Select onValueChange (handleSilenceModeChange)
// - page mode rendering (availablePages.map with real pages)
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { ThemeProvider } from "next-themes";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mockOutputSettings, mockPages, mockTransitionSettings } from "./mocks/handlers";
import { server } from "./mocks/server";

vi.mock("next/navigation", () => ({
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

import { GeneralSettings } from "@/components/general-settings";

const API_BASE = "/api";

function allSettings(silenceOverrides: Record<string, unknown> = {}) {
  return {
    general: {
      timezone: "America/Los_Angeles",
      refresh_interval_seconds: 300,
      output_target: "board",
    },
    silence_schedule: {
      config: {
        enabled: true,
        start_time: "04:00+00:00",
        end_time: "15:00+00:00",
        mode: "indicator",
        page_id: null,
        indicator_text: "SNOOZING",
        indicator_position: "center",
        ...silenceOverrides,
      },
    },
    polling: { interval_seconds: 300, board_read_interval_local: 30, board_read_interval_cloud: 180 },
    transitions: mockTransitionSettings,
    output: mockOutputSettings,
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
  };
}

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

describe("GeneralSettings - silence interaction handlers", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    server.use(http.get(`${API_BASE}/settings/all`, () => HttpResponse.json(allSettings())));
  });

  afterEach(() => server.resetHandlers());

  it("triggers handleSilenceTimeChange for start when TimePicker hour is selected", async () => {
    const user = userEvent.setup();
    render(<GeneralSettings />, { wrapper: TestWrapper });

    const startPicker = await screen.findByLabelText(/Start Time/i);
    await user.click(startPicker);

    // "3 AM" appears only in hour options, not in quick presets — click fires onChange
    const threeAm = await screen.findByText("3 AM");
    await user.click(threeAm);
  });

  it("triggers handleSilenceTimeChange for end when TimePicker hour is selected", async () => {
    const user = userEvent.setup();
    render(<GeneralSettings />, { wrapper: TestWrapper });

    const endPicker = await screen.findByLabelText(/End Time/i);
    await user.click(endPicker);

    // "5 PM" appears only in hour options, not in quick presets — click fires onChange
    const fivePm = await screen.findByText("5 PM");
    await user.click(fivePm);
  });

  it("triggers handleSilenceModeChange when mode select changes to freeze", async () => {
    const user = userEvent.setup();
    render(<GeneralSettings />, { wrapper: TestWrapper });

    const modeSelect = await screen.findByRole("combobox", { name: /While Silenced/i });
    await user.click(modeSelect);

    const freezeOption = await screen.findByText("Leave board unchanged");
    await user.click(freezeOption);

    // After switching to freeze, the indicator text/position controls disappear
    await waitFor(() => expect(screen.queryByLabelText(/message text/i)).not.toBeInTheDocument());
  });

  it("renders available pages in page mode selector", async () => {
    server.use(
      http.get(`${API_BASE}/settings/all`, () => HttpResponse.json(allSettings({ mode: "page" }))),
      http.get(`${API_BASE}/pages`, () => HttpResponse.json(mockPages)),
    );

    const user = userEvent.setup();
    render(<GeneralSettings />, { wrapper: TestWrapper });

    // Wait for the silence page select to appear
    const pageSelect = await screen.findByRole("combobox", { name: /Silence Page/i });
    await user.click(pageSelect);

    const listbox = await screen.findByRole("listbox");
    expect(within(listbox).getByText("Weather Page")).toBeInTheDocument();
  });
});
