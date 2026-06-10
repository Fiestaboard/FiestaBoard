import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

const mockTriggerWizard = vi.fn();
vi.mock("@/components/wizard-provider", () => ({
  useWizard: () => ({
    isWizardActive: false,
    triggerWizard: mockTriggerWizard,
  }),
  WizardProvider: ({ children }: { children: React.ReactNode }) => children,
}));

const mockPush = vi.fn();
vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
    back: vi.fn(),
  }),
}));

import Home from "../../app/routes/home";

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

describe("Home page - board not configured banner", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows info banner when board is not configured", async () => {
    server.use(
      http.get(`${API_BASE}/config/validate`, () =>
        HttpResponse.json({
          valid: false,
          is_first_run: true,
          errors: ["missing api key"],
          missing_fields: ["api_key"],
        }),
      ),
    );

    render(<Home />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("No board configured")).toBeInTheDocument();
      expect(screen.getByText(/Your board is not set up yet/)).toBeInTheDocument();
    });
  });

  it("does not show info banner when board is configured", async () => {
    server.use(
      http.get(`${API_BASE}/config/validate`, () =>
        HttpResponse.json({
          valid: true,
          is_first_run: false,
          errors: [],
          missing_fields: [],
        }),
      ),
    );

    render(<Home />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });

    expect(screen.queryByText("No board configured")).not.toBeInTheDocument();
  });

  it("shows Run Setup Wizard button that triggers wizard", async () => {
    server.use(
      http.get(`${API_BASE}/config/validate`, () =>
        HttpResponse.json({
          valid: false,
          is_first_run: false,
          errors: ["missing api key"],
          missing_fields: ["api_key"],
        }),
      ),
    );

    const user = userEvent.setup();
    render(<Home />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("No board configured")).toBeInTheDocument();
    });

    const wizardBtn = screen.getByRole("button", {
      name: /Run Setup Wizard/i,
    });
    await user.click(wizardBtn);

    expect(mockTriggerWizard).toHaveBeenCalledTimes(1);
  });

  it("does not show banner when API call fails", async () => {
    server.use(http.get(`${API_BASE}/config/validate`, () => new HttpResponse(null, { status: 500 })));

    const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(<Home />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Dashboard")).toBeInTheDocument();
    });

    // Wait a bit to ensure async check has completed
    await new Promise((r) => setTimeout(r, 100));
    expect(screen.queryByText("No board configured")).not.toBeInTheDocument();

    consoleSpy.mockRestore();
  });
});
