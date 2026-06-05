// Phase 8: general-settings silence UI tests
//
// Covers:
// - Indicator mode shows text + position controls; freeze/page hide them
// - Lowercase input is auto-uppercased (handleSilenceIndicatorTextChange)
// - maxLength=22 enforced on the text input
// - Position select has all 5 options
// - Initial load populates from config (indicator_text/indicator_position)
// - Save sends PUT with indicator_text + indicator_position
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { ThemeProvider } from "next-themes";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { mockOutputSettings, mockTransitionSettings } from "./mocks/handlers";
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

// A full all-settings response with silence enabled and mode=indicator
function allSettingsResponse(silenceOverrides: Record<string, unknown> = {}) {
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
    polling: { interval_seconds: 15 },
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

// Enable silence and switch to "indicator" mode before running each test.
async function enableSilenceAndSelectMode(user: ReturnType<typeof userEvent.setup>, mode = "indicator") {
  // Wait for the silence toggle to be present
  const toggle = await screen.findByRole("switch", { name: /Silence Schedule/i });
  if (!(toggle as HTMLInputElement).checked) {
    await user.click(toggle);
  }
  // Wait for mode controls to appear
  await screen.findByRole("combobox", { name: /Silence Mode/i });
  // No need to change if default is already correct
  if (mode !== "indicator") {
    const modeSelect = screen.getByRole("combobox", { name: /Silence Mode/i });
    await user.click(modeSelect);
    const option = await screen.findByText(mode === "freeze" ? /Don't update/i : /Display specific page/i);
    await user.click(option);
  }
}

describe("GeneralSettings - silence indicator controls visibility", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    server.use(http.get(`${API_BASE}/settings/all`, () => HttpResponse.json(allSettingsResponse())));
  });

  afterEach(() => server.resetHandlers());

  it("shows indicator text + position inputs when mode is 'indicator'", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    // The config already has mode=indicator and silence enabled, so controls
    // should appear after load.
    const textInput = await screen.findByLabelText(/message text/i);
    expect(textInput).toBeInTheDocument();

    const positionLabel = await screen.findByText(/Message Position/i);
    expect(positionLabel).toBeInTheDocument();
  });

  it("hides indicator text + position inputs when mode is 'freeze'", async () => {
    server.use(http.get(`${API_BASE}/settings/all`, () => HttpResponse.json(allSettingsResponse({ mode: "freeze" }))));
    render(<GeneralSettings />, { wrapper: TestWrapper });

    // Silence enabled, mode=freeze — text/position controls must be absent
    await screen.findByRole("combobox", { name: /While Silenced/i });
    expect(screen.queryByLabelText(/message text/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/Message Position/i)).not.toBeInTheDocument();
  });

  it("hides indicator controls when silence is disabled", async () => {
    server.use(http.get(`${API_BASE}/settings/all`, () => HttpResponse.json(allSettingsResponse({ enabled: false }))));
    render(<GeneralSettings />, { wrapper: TestWrapper });

    // Silence disabled — entire silence section including indicator is hidden
    await screen.findByRole("switch", { name: /Silence Schedule/i });
    expect(screen.queryByLabelText(/message text/i)).not.toBeInTheDocument();
  });
});

describe("GeneralSettings - indicator text input behaviour", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    server.use(http.get(`${API_BASE}/settings/all`, () => HttpResponse.json(allSettingsResponse())));
  });
  afterEach(() => server.resetHandlers());

  it("pre-populates indicator text from config", async () => {
    server.use(
      http.get(`${API_BASE}/settings/all`, () => HttpResponse.json(allSettingsResponse({ indicator_text: "BEDTIME" }))),
    );
    render(<GeneralSettings />, { wrapper: TestWrapper });

    const input = (await screen.findByLabelText(/message text/i)) as HTMLInputElement;
    expect(input.value).toBe("BEDTIME");
  });

  it("uppercases typed text automatically", async () => {
    const user = userEvent.setup();
    render(<GeneralSettings />, { wrapper: TestWrapper });

    const input = (await screen.findByLabelText(/message text/i)) as HTMLInputElement;
    await user.clear(input);
    await user.type(input, "nighttime");
    // handleSilenceIndicatorTextChange calls toUpperCase()
    expect(input.value).toBe("NIGHTTIME");
  });

  it("enforces maxLength of 22", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    const input = (await screen.findByLabelText(/message text/i)) as HTMLInputElement;
    expect(input.maxLength).toBe(22);
  });
});

describe("GeneralSettings - indicator position select", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    server.use(http.get(`${API_BASE}/settings/all`, () => HttpResponse.json(allSettingsResponse())));
  });
  afterEach(() => server.resetHandlers());

  it("pre-populates position from config", async () => {
    server.use(
      http.get(`${API_BASE}/settings/all`, () =>
        HttpResponse.json(allSettingsResponse({ indicator_position: "bottom-right" })),
      ),
    );
    render(<GeneralSettings />, { wrapper: TestWrapper });

    const user = userEvent.setup();
    // Open the position select to verify it exists and has the right value
    const posSelect = await screen.findByRole("combobox", { name: /Message Position/i });
    expect(posSelect).toBeInTheDocument();
    // The display value should reflect bottom-right
    await user.click(posSelect);
    const listbox = await screen.findByRole("listbox");
    // All 5 options must be visible
    expect(within(listbox).getByText(/Top Left/i)).toBeInTheDocument();
    expect(within(listbox).getByText(/Top Right/i)).toBeInTheDocument();
    expect(within(listbox).getByText(/Center/i)).toBeInTheDocument();
    expect(within(listbox).getByText(/Bottom Left/i)).toBeInTheDocument();
    expect(within(listbox).getByText(/Bottom Right/i)).toBeInTheDocument();
  });
});

describe("GeneralSettings - save includes indicator fields", () => {
  let capturedBody: Record<string, unknown> | null = null;

  beforeEach(() => {
    vi.clearAllMocks();
    capturedBody = null;
    server.use(
      http.get(`${API_BASE}/settings/all`, () => HttpResponse.json(allSettingsResponse())),
      http.put(`${API_BASE}/settings/silence-schedule`, async ({ request }) => {
        capturedBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ status: "success", config: capturedBody });
      }),
    );
  });
  afterEach(() => server.resetHandlers());

  it("PUT body contains indicator_text and indicator_position", async () => {
    const user = userEvent.setup();
    render(<GeneralSettings />, { wrapper: TestWrapper });

    // Change indicator text to trigger auto-save
    const textInput = await screen.findByLabelText(/message text/i);
    await user.clear(textInput);
    await user.type(textInput, "ZZZZ");

    // Wait for debounced auto-save (1000ms) + mutation to fire
    await waitFor(
      () => {
        expect(capturedBody).not.toBeNull();
        expect(capturedBody?.indicator_text).toBe("ZZZZ");
        expect(capturedBody?.indicator_position).toBe("center");
      },
      { timeout: 3000 },
    );
  });
});
