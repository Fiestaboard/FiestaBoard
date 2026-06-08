import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { ThemeProvider } from "@/hooks/use-theme";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "./mocks/server";

const API_BASE = "/api";

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

import { GeneralSettings } from "@/components/general-settings";

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

describe("GeneralSettings — board read intervals", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    server.resetHandlers();
  });

  it("renders board-read-local and board-read-cloud inputs with values from API", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(document.getElementById("board-read-local")).toBeInTheDocument();
      expect(document.getElementById("board-read-cloud")).toBeInTheDocument();
    });

    const localInput = document.getElementById("board-read-local") as HTMLInputElement;
    const cloudInput = document.getElementById("board-read-cloud") as HTMLInputElement;
    expect(parseInt(localInput.value, 10)).toBe(30);
    expect(parseInt(cloudInput.value, 10)).toBe(180);
  });

  it("onChange updates local interval when value is a valid number", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    // Wait for the input AND for useDeferredValue to settle on the API value (30)
    // before firing the change, so a late deferred update can't overwrite it.
    await waitFor(() => {
      const el = document.getElementById("board-read-local") as HTMLInputElement;
      expect(el).toBeInTheDocument();
      expect(parseInt(el.value, 10)).toBe(30);
    });
    // Flush all pending React state updates (including deferred ones) before
    // interacting, so a late deferred update from the API can't overwrite the
    // user's change. The default (30) matches the API value, so waitFor above
    // may return before the deferred React Query update has settled.
    await act(async () => {});

    const input = document.getElementById("board-read-local") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "45" } });

    await waitFor(() => {
      expect(parseInt(input.value, 10)).toBe(45);
    });
  });

  it("onChange updates cloud interval when value is a valid number", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    // Wait for the input AND for useDeferredValue to settle on the API value (180)
    // before firing the change, so a late deferred update can't overwrite it.
    await waitFor(() => {
      const el = document.getElementById("board-read-cloud") as HTMLInputElement;
      expect(el).toBeInTheDocument();
      expect(parseInt(el.value, 10)).toBe(180);
    });
    // Flush all pending React state updates (including deferred ones) before
    // interacting, so a late deferred update from the API can't overwrite the
    // user's change.
    await act(async () => {});

    const input = document.getElementById("board-read-cloud") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "90" } });

    await waitFor(() => {
      expect(parseInt(input.value, 10)).toBe(90);
    });
  });

  it("shows warning when cloud interval is below 60 seconds", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    // Wait for the API value to load (180) before firing the change,
    // then flush deferred updates so a late React re-render can't overwrite it.
    await waitFor(() => {
      const el = document.getElementById("board-read-cloud") as HTMLInputElement;
      expect(el).toBeInTheDocument();
      expect(parseInt(el.value, 10)).toBe(180);
    });
    // Flush all deferred React state BEFORE the change so the deferred update
    // from the API doesn't run after our fireEvent and reset cloud back to 180.
    await act(async () => {});

    const input = document.getElementById("board-read-cloud") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "30" } });

    await waitFor(() => {
      expect(screen.getByText(/excessive load on Vestaboard/i)).toBeInTheDocument();
    });
  });

  it("does not show warning when cloud interval is 60 or above", async () => {
    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => expect(document.getElementById("board-read-cloud")).toBeInTheDocument());

    // Default is 180 — warning should not be visible
    expect(screen.queryByText(/excessive load on Vestaboard/i)).not.toBeInTheDocument();
  });

  it("onBlur for local input triggers update mutation", async () => {
    let capturedBody: unknown;
    server.use(
      http.put(`${API_BASE}/settings/polling`, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          status: "success",
          settings: { interval_seconds: 30, board_read_interval_local: 45 },
          requires_restart: false,
        });
      }),
    );

    render(<GeneralSettings />, { wrapper: TestWrapper });

    // Wait for the deferred polling settings to fully load and sync to state
    const input = await waitFor(() => {
      const el = document.getElementById("board-read-local") as HTMLInputElement;
      expect(el).toBeInTheDocument();
      expect(el.value).toBe("30");
      return el;
    });

    fireEvent.change(input, { target: { value: "45" } });
    await waitFor(() => expect(parseInt(input.value, 10)).toBe(45));
    await act(async () => {});
    fireEvent.blur(input);

    await waitFor(() => {
      expect(capturedBody).toMatchObject({ board_read_interval_local: 45 });
    });
  });

  it("onBlur for cloud input triggers update mutation", async () => {
    let capturedBody: unknown;
    server.use(
      http.put(`${API_BASE}/settings/polling`, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          status: "success",
          settings: { interval_seconds: 30, board_read_interval_cloud: 90 },
          requires_restart: false,
        });
      }),
    );

    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => expect(document.getElementById("board-read-cloud")).toBeInTheDocument());

    const input = document.getElementById("board-read-cloud") as HTMLInputElement;
    await waitFor(() => expect(parseInt(input.value, 10)).toBe(180));
    fireEvent.change(input, { target: { value: "90" } });
    // Flush all pending React state updates (including deferred ones) before blur
    // so the blur handler reads the updated value, not the initial default.
    await waitFor(() => expect(parseInt(input.value, 10)).toBe(90));
    await act(async () => {});
    fireEvent.blur(input);

    await waitFor(() => {
      expect(capturedBody).toMatchObject({ board_read_interval_cloud: 90 });
    });
  });

  it("onBlur clamps local interval to minimum 20 if below", async () => {
    let capturedBody: unknown;
    server.use(
      http.put(`${API_BASE}/settings/polling`, async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({
          status: "success",
          settings: {},
          requires_restart: false,
        });
      }),
    );

    render(<GeneralSettings />, { wrapper: TestWrapper });

    await waitFor(() => expect(document.getElementById("board-read-local")).toBeInTheDocument());

    const input = document.getElementById("board-read-local") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "5" } });
    // Flush React pending state updates before blur so the handler reads the new value
    await act(async () => {});
    fireEvent.blur(input);

    await waitFor(() => {
      expect(capturedBody).toMatchObject({ board_read_interval_local: 20 });
    });
  });
});
