import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

import { LocationSettingsCard } from "@/components/settings/location-settings";

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

// Helper to create a mock geolocation object
function mockGeolocation(overrides: Partial<typeof navigator.geolocation> = {}) {
  return {
    getCurrentPosition: vi.fn(),
    watchPosition: vi.fn(),
    clearWatch: vi.fn(),
    ...overrides,
  };
}

// Helper to build a GeolocationPosition-like mock object
function mockPosition(latitude: number, longitude: number): GeolocationPosition {
  return {
    coords: {
      latitude,
      longitude,
      accuracy: 10,
      altitude: null,
      altitudeAccuracy: null,
      heading: null,
      speed: null,
    },
    timestamp: Date.now(),
  };
}

// Helper to build a GeolocationPositionError-like mock object
function mockGeoError(code: 1 | 2 | 3, message: string): GeolocationPositionError {
  return {
    code,
    message,
    PERMISSION_DENIED: 1,
    POSITION_UNAVAILABLE: 2,
    TIMEOUT: 3,
  };
}

describe("LocationSettingsCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    // Restore geolocation after each test
    Object.defineProperty(navigator, "geolocation", {
      value: undefined,
      configurable: true,
      writable: true,
    });
  });

  it("renders the location card with title and description", async () => {
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Location")).toBeInTheDocument();
      expect(screen.getByText(/sunrise\/sunset-based schedules/)).toBeInTheDocument();
    });
  });

  it("renders latitude and longitude inputs", async () => {
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByLabelText("Latitude")).toBeInTheDocument();
      expect(screen.getByLabelText("Longitude")).toBeInTheDocument();
    });
  });

  it("shows empty inputs when no location is configured", async () => {
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      const latInput = screen.getByLabelText("Latitude") as HTMLInputElement;
      const lonInput = screen.getByLabelText("Longitude") as HTMLInputElement;
      expect(latInput.value).toBe("");
      expect(lonInput.value).toBe("");
    });
  });

  it("pre-populates inputs when location is already saved", async () => {
    server.use(
      http.get(`${API_BASE}/settings/location`, () => HttpResponse.json({ latitude: 40.7128, longitude: -74.006 })),
    );

    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      const latInput = screen.getByLabelText("Latitude") as HTMLInputElement;
      const lonInput = screen.getByLabelText("Longitude") as HTMLInputElement;
      expect(latInput.value).toBe("40.7128");
      expect(lonInput.value).toBe("-74.006");
    });
  });

  it("shows the 'Use my location' button", async () => {
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /use my location/i })).toBeInTheDocument();
    });
  });

  it("shows the Save button", async () => {
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save/i })).toBeInTheDocument();
    });
  });

  it("shows the Clear button when location is already configured", async () => {
    server.use(
      http.get(`${API_BASE}/settings/location`, () => HttpResponse.json({ latitude: 40.7128, longitude: -74.006 })),
    );

    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /clear/i })).toBeInTheDocument();
    });
  });

  it("does not show the Clear button when no location is configured", async () => {
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByText("Location")).toBeInTheDocument();
    });

    expect(screen.queryByRole("button", { name: /clear/i })).not.toBeInTheDocument();
  });

  it("Save button is disabled when form is not dirty", async () => {
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      const saveBtn = screen.getByRole("button", { name: /save/i });
      expect(saveBtn).toBeDisabled();
    });
  });

  it("Save button becomes enabled when user changes an input", async () => {
    const user = userEvent.setup();
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByLabelText("Latitude")).toBeInTheDocument();
    });

    const latInput = screen.getByLabelText("Latitude");
    await user.type(latInput, "51.5074");

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save/i })).not.toBeDisabled();
    });
  });

  it("calls getCurrentPosition when 'Use my location' is clicked", async () => {
    const geo = mockGeolocation();
    Object.defineProperty(navigator, "geolocation", {
      value: geo,
      configurable: true,
      writable: true,
    });

    const user = userEvent.setup();
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /use my location/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /use my location/i }));

    expect(geo.getCurrentPosition).toHaveBeenCalledTimes(1);
  });

  it("fills lat/lon fields from geolocation success response", async () => {
    const geo = mockGeolocation({
      getCurrentPosition: vi.fn((successCb) => {
        successCb(mockPosition(51.507351, -0.127758));
      }),
    });
    Object.defineProperty(navigator, "geolocation", {
      value: geo,
      configurable: true,
      writable: true,
    });

    const user = userEvent.setup();
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /use my location/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /use my location/i }));

    await waitFor(() => {
      const latInput = screen.getByLabelText("Latitude") as HTMLInputElement;
      const lonInput = screen.getByLabelText("Longitude") as HTMLInputElement;
      expect(latInput.value).toBe("51.507351");
      expect(lonInput.value).toBe("-0.127758");
    });
  });

  it("marks form dirty after geolocation success so Save becomes enabled", async () => {
    const geo = mockGeolocation({
      getCurrentPosition: vi.fn((successCb) => {
        successCb(mockPosition(51.507351, -0.127758));
      }),
    });
    Object.defineProperty(navigator, "geolocation", {
      value: geo,
      configurable: true,
      writable: true,
    });

    const user = userEvent.setup();
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /use my location/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /use my location/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /save/i })).not.toBeDisabled();
    });
  });

  it("shows error toast when geolocation permission is denied", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "error");

    const geo = mockGeolocation({
      getCurrentPosition: vi.fn((_successCb, errorCb) => {
        errorCb(mockGeoError(1, "User denied geolocation"));
      }),
    });
    Object.defineProperty(navigator, "geolocation", {
      value: geo,
      configurable: true,
      writable: true,
    });

    const user = userEvent.setup();
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /use my location/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /use my location/i }));

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith("Location access was denied");
    });

    toastSpy.mockRestore();
  });

  it("shows error toast when geolocation is unavailable", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "error");

    const geo = mockGeolocation({
      getCurrentPosition: vi.fn((_successCb, errorCb) => {
        errorCb(mockGeoError(2, "Position unavailable"));
      }),
    });
    Object.defineProperty(navigator, "geolocation", {
      value: geo,
      configurable: true,
      writable: true,
    });

    const user = userEvent.setup();
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /use my location/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /use my location/i }));

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith("Location is not available");
    });

    toastSpy.mockRestore();
  });

  it("shows error toast when browser does not support geolocation", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "error");

    Object.defineProperty(navigator, "geolocation", {
      value: undefined,
      configurable: true,
      writable: true,
    });

    const user = userEvent.setup();
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /use my location/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /use my location/i }));

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith("Location is not available");
    });

    toastSpy.mockRestore();
  });

  it("saves lat/lon to API when Save is clicked", async () => {
    let savedPayload: Record<string, unknown> | undefined;
    server.use(
      http.put(`${API_BASE}/settings/location`, async ({ request }) => {
        savedPayload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          status: "success",
          settings: { latitude: 51.5074, longitude: -0.1278 },
        });
      }),
    );

    const user = userEvent.setup();
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByLabelText("Latitude")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("Latitude"), "51.5074");
    await user.type(screen.getByLabelText("Longitude"), "-0.1278");

    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(savedPayload?.latitude).toBeCloseTo(51.5074);
      expect(savedPayload?.longitude).toBeCloseTo(-0.1278);
    });
  });

  it("shows success toast after saving", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "success");

    const user = userEvent.setup();
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByLabelText("Latitude")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("Latitude"), "51.5074");
    await user.type(screen.getByLabelText("Longitude"), "-0.1278");

    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith("Location settings saved");
    });

    toastSpy.mockRestore();
  });

  it("clears the location when Clear is clicked", async () => {
    let clearedPayload: Record<string, unknown> | undefined;
    server.use(
      http.get(`${API_BASE}/settings/location`, () => HttpResponse.json({ latitude: 40.7128, longitude: -74.006 })),
      http.put(`${API_BASE}/settings/location`, async ({ request }) => {
        clearedPayload = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ status: "success", settings: { latitude: null, longitude: null } });
      }),
    );

    const user = userEvent.setup();
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /clear/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /clear/i }));

    await waitFor(() => {
      expect(clearedPayload?.latitude).toBeNull();
      expect(clearedPayload?.longitude).toBeNull();
    });
  });

  it("shows validation error toast for out-of-range latitude", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "error");

    const user = userEvent.setup();
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByLabelText("Latitude")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("Latitude"), "95");

    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith("Latitude must be a number between -90 and 90");
    });

    toastSpy.mockRestore();
  });

  it("shows validation error toast for out-of-range longitude", async () => {
    const toastSpy = vi.spyOn((await import("sonner")).toast, "error");

    const user = userEvent.setup();
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByLabelText("Latitude")).toBeInTheDocument();
    });

    await user.type(screen.getByLabelText("Latitude"), "40");
    await user.type(screen.getByLabelText("Longitude"), "200");

    await user.click(screen.getByRole("button", { name: /save/i }));

    await waitFor(() => {
      expect(toastSpy).toHaveBeenCalledWith("Longitude must be a number between -180 and 180");
    });

    toastSpy.mockRestore();
  });

  it("passes the 10-second timeout option to getCurrentPosition", async () => {
    const geo = mockGeolocation();
    Object.defineProperty(navigator, "geolocation", {
      value: geo,
      configurable: true,
      writable: true,
    });

    const user = userEvent.setup();
    render(<LocationSettingsCard />, { wrapper: TestWrapper });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /use my location/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /use my location/i }));

    expect(geo.getCurrentPosition).toHaveBeenCalledWith(
      expect.any(Function),
      expect.any(Function),
      expect.objectContaining({ timeout: 10000 }),
    );
  });
});
