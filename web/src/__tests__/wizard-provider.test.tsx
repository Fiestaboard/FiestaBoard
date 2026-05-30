import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";

// Mock next/navigation. ``currentPathname`` is mutable so individual tests
// can simulate a route transition (e.g. /login -> /) without remounting the
// provider — the WizardProvider lives in the root layout, which doesn't
// remount on client-side navigation, so the bug we're guarding against is
// "didn't re-check after the auth picker finished".
let currentPathname = "/";
vi.mock("next/navigation", () => ({
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

// Stub the wizard so we don't have to stand up Aurora / WebGL in jsdom.
vi.mock("@/components/wizard", () => ({
  SetupWizard: () => <div data-testid="wizard" />,
}));

import { WizardProvider, useWizard } from "@/components/wizard-provider";

function Probe() {
  const { isWizardActive } = useWizard();
  return <div data-testid="probe">{isWizardActive ? "wizard" : "no-wizard"}</div>;
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
});
