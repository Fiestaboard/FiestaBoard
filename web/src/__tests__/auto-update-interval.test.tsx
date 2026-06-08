import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AutoUpdateIntervalCard } from "@/components/settings/auto-update-interval";

import { server } from "./mocks/server";

const API_BASE = "/api";

const toastMock = vi.hoisted(() => ({
  success: vi.fn(),
  info: vi.fn(),
  error: vi.fn(),
  warning: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: toastMock,
  Toaster: () => null,
}));

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });

  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

describe("AutoUpdateIntervalCard – manual Check now button", () => {
  beforeEach(() => {
    toastMock.success.mockClear();
    toastMock.info.mockClear();
    toastMock.error.mockClear();
  });

  it("renders a Check now button alongside the interval selector", async () => {
    render(<AutoUpdateIntervalCard />, { wrapper: TestWrapper });

    const button = await screen.findByRole("button", { name: /check now/i });
    expect(button).toBeInTheDocument();
    expect(button).not.toBeDisabled();
  });

  it("shows a success toast when the manual check finds no update", async () => {
    render(<AutoUpdateIntervalCard />, { wrapper: TestWrapper });

    const button = await screen.findByRole("button", { name: /check now/i });
    await userEvent.click(button);

    await waitFor(() => {
      expect(toastMock.success).toHaveBeenCalled();
    });
    const msg = toastMock.success.mock.calls[0][0] as string;
    expect(msg).toMatch(/up to date/i);
    expect(toastMock.info).not.toHaveBeenCalled();
    expect(toastMock.error).not.toHaveBeenCalled();
  });

  it("shows an info toast when the manual check finds an update", async () => {
    server.use(
      http.get(`${API_BASE}/system/update-check`, () => {
        return HttpResponse.json({
          current_version: "2.0.1",
          latest_version: "2.1.0",
          update_available: true,
          package_url: "https://github.com/Fiestaboard/FiestaBoard/releases/latest",
          error: null,
          is_production: true,
        });
      }),
    );

    render(<AutoUpdateIntervalCard />, { wrapper: TestWrapper });

    const button = await screen.findByRole("button", { name: /check now/i });
    await userEvent.click(button);

    await waitFor(() => {
      expect(toastMock.info).toHaveBeenCalled();
    });
    const msg = toastMock.info.mock.calls[0][0] as string;
    expect(msg).toMatch(/2\.1\.0/);
  });

  it("shows an error toast when the manual check returns an error payload", async () => {
    server.use(
      http.get(`${API_BASE}/system/update-check`, () => {
        return HttpResponse.json({
          current_version: "2.0.1",
          latest_version: null,
          update_available: false,
          package_url: "https://github.com/Fiestaboard/FiestaBoard/releases/latest",
          error: "network unreachable",
          is_production: true,
        });
      }),
    );

    render(<AutoUpdateIntervalCard />, { wrapper: TestWrapper });

    const button = await screen.findByRole("button", { name: /check now/i });
    await userEvent.click(button);

    await waitFor(() => {
      expect(toastMock.error).toHaveBeenCalled();
    });
    const msg = toastMock.error.mock.calls[0][0] as string;
    expect(msg).toMatch(/network unreachable/);
  });
});
