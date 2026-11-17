import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { toast, Toaster } from "sonner";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "./mocks/server";

// Mock next/navigation. ``currentPathname`` is mutable so individual tests
// can simulate a route transition (e.g. /login -> /) without remounting the
// provider — the WizardProvider lives in the root layout, which doesn't
// remount on client-side navigation, so the bug we're guarding against is
// "didn't re-check after the auth picker finished".
let currentPathname = "/";
vi.mock("@/hooks/use-router", () => ({
  usePathname: () => currentPathname,
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

// Stub the wizard: these tests cover the provider's open/close contract, not
// the multi-step flow. (It used to be stubbed to avoid standing up Aurora's
// WebGL context in jsdom; 4.0.0 retired Aurora, but the stub still earns its
// keep by keeping this suite off the whole wizard tree.)
vi.mock("@/components/wizard", () => ({
  SetupWizard: () => <div data-testid="wizard" />,
}));

import { useWizard, WizardProvider } from "@/components/wizard-provider";

function Probe() {
  const { isWizardActive, triggerWizard } = useWizard();
  return (
    <>
      <div data-testid="probe">{isWizardActive ? "wizard" : "no-wizard"}</div>
      <button onClick={triggerWizard}>Run setup again</button>
    </>
  );
}

function firstRunValidation() {
  return http.get("/api/config/validate", () =>
    HttpResponse.json({
      valid: false,
      is_first_run: true,
      errors: ["missing board"],
      missing_fields: ["board.host"],
    }),
  );
}

describe("WizardProvider", () => {
  beforeEach(() => {
    currentPathname = "/";
    localStorage.clear();
  });

  it("does not render the wizard while the user is on /login", async () => {
    currentPathname = "/login";
    server.use(firstRunValidation());

    render(
      <WizardProvider>
        <Probe />
      </WizardProvider>,
    );

    // Children render normally (no wizard) — /login owns its own UI.
    await screen.findByTestId("probe");
    expect(screen.getByTestId("probe").textContent).toBe("no-wizard");
  });

  it("renders the wizard after the user transitions from /login to / on a first-run device", async () => {
    currentPathname = "/login";
    server.use(firstRunValidation());

    const { rerender } = render(
      <WizardProvider>
        <Probe />
      </WizardProvider>,
    );

    await screen.findByTestId("probe");
    expect(screen.getByTestId("probe").textContent).toBe("no-wizard");

    // Simulate the LoginPage doing router.replace("/") after the
    // first-run picker resolves (skip or set-up-credentials).
    currentPathname = "/";
    rerender(
      <WizardProvider>
        <Probe />
      </WizardProvider>,
    );

    // The provider must re-run shouldShowWizard now that we're off /login,
    // and surface the wizard since the server says is_first_run=true.
    await waitFor(() => {
      expect(screen.getByTestId("wizard")).toBeInTheDocument();
    });
    // Wizard replaces the children entirely, so the probe is gone.
    expect(screen.queryByTestId("probe")).not.toBeInTheDocument();
  });

  it("does not render the wizard on / when the device is already configured", async () => {
    currentPathname = "/";
    server.use(
      http.get("/api/config/validate", () =>
        HttpResponse.json({
          valid: true,
          is_first_run: false,
          errors: [],
          missing_fields: [],
        }),
      ),
    );

    render(
      <WizardProvider>
        <Probe />
      </WizardProvider>,
    );

    await waitFor(() => {
      expect(screen.getByTestId("probe").textContent).toBe("no-wizard");
    });
  });
  it("checks the fleet before manual rerun and never flashes setup over a real display", async () => {
    let release: (() => void) | undefined;
    let requested = false;
    server.use(
      http.get("/api/config/validate", () =>
        HttpResponse.json({ valid: true, is_first_run: false, errors: [], missing_fields: [] }),
      ),
      http.get("/api/settings/board", async () => {
        requested = true;
        await new Promise<void>((resolve) => {
          release = resolve;
        });
        return HttpResponse.json({
          boards: [{ id: "tv", name: "Living room", device_type: "panel", output: "fiestapanel", output_config: {} }],
        });
      }),
    );
    render(
      <WizardProvider>
        <Probe />
      </WizardProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Run setup again" }));
    expect(screen.queryByTestId("wizard")).not.toBeInTheDocument();
    await waitFor(() => expect(requested).toBe(true));
    await act(async () => {
      release?.();
    });
    expect(await screen.findByTestId("probe")).toHaveTextContent("no-wizard");
  });

  it("allows rerun when the only board is an untouched legacy placeholder", async () => {
    server.use(
      http.get("/api/config/validate", () =>
        HttpResponse.json({ valid: true, is_first_run: false, errors: [], missing_fields: [] }),
      ),
    );
    render(
      <WizardProvider>
        <Probe />
      </WizardProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "Run setup again" }));
    expect(await screen.findByTestId("wizard")).toBeInTheDocument();
  });
});

it("shows a retryable error if a manual setup eligibility check cannot reach the hub", async () => {
  server.use(
    http.get("/api/config/validate", () =>
      HttpResponse.json({ valid: true, is_first_run: false, errors: [], missing_fields: [] }),
    ),
    http.get("/api/settings/board", () => HttpResponse.json({ detail: "Unavailable" }, { status: 503 })),
  );
  render(
    <WizardProvider>
      <Probe />
      <Toaster />
    </WizardProvider>,
  );
  await userEvent.click(await screen.findByRole("button", { name: "Run setup again" }));
  await screen.findByText("Couldn’t check your displays. Check your connection and try setup again.");
  expect(screen.queryByTestId("wizard")).not.toBeInTheDocument();
  server.use(http.get("/api/settings/board", () => HttpResponse.json({ boards: [] })));
  await userEvent.click(screen.getByRole("button", { name: "Run setup again" }));
  await screen.findByTestId("wizard");
  toast.dismiss();
});
