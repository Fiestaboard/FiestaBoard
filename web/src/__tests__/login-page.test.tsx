import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "./mocks/server";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: replaceMock,
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => new URLSearchParams(""),
  usePathname: () => "/login",
}));

import LoginPage from "@/app/login/page";

function makeStatus(overrides: Partial<{
  enabled: boolean;
  setup_required: boolean;
  authenticated: boolean;
  username: string | null;
  mode: "enabled" | "disabled" | "undecided";
  first_run: boolean;
}>) {
  return {
    enabled: true,
    setup_required: true,
    authenticated: false,
    username: null,
    mode: "enabled" as const,
    first_run: false,
    ...overrides,
  };
}

describe("LoginPage first-run picker", () => {
  beforeEach(() => {
    replaceMock.mockReset();
  });

  it("renders the picker when the server reports first_run=true", async () => {
    server.use(
      http.get("/api/auth/status", () =>
        HttpResponse.json(
          makeStatus({ mode: "undecided", first_run: true, setup_required: true }),
        ),
      ),
    );
    render(<LoginPage />);

    await screen.findByText(/Secure this FiestaBoard\?/i);
    expect(
      screen.getByRole("button", { name: /Enable login/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Continue without login/i }),
    ).toBeInTheDocument();
  });

  it("clicking 'Enable login' switches to the setup form", async () => {
    server.use(
      http.get("/api/auth/status", () =>
        HttpResponse.json(
          makeStatus({ mode: "undecided", first_run: true, setup_required: true }),
        ),
      ),
    );
    render(<LoginPage />);

    await screen.findByText(/Secure this FiestaBoard\?/i);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Enable login/i }));

    await screen.findByText(/Create administrator/i);
  });

  it("clicking 'Continue without login' POSTs preference and redirects", async () => {
    let body: { enabled?: boolean } | null = null;
    server.use(
      http.get("/api/auth/status", () =>
        HttpResponse.json(
          makeStatus({ mode: "undecided", first_run: true, setup_required: true }),
        ),
      ),
      http.post("/api/auth/preference", async ({ request }) => {
        body = (await request.json()) as { enabled?: boolean };
        return HttpResponse.json({ status: "ok" });
      }),
    );
    render(<LoginPage />);

    await screen.findByText(/Secure this FiestaBoard\?/i);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Continue without login/i }));

    await waitFor(() => {
      expect(body).toEqual({ enabled: false });
    });
    expect(replaceMock).toHaveBeenCalledWith("/");
  });

  it("renders the sign-in form for an existing user (no first_run)", async () => {
    server.use(
      http.get("/api/auth/status", () =>
        HttpResponse.json(
          makeStatus({ mode: "enabled", first_run: false, setup_required: false }),
        ),
      ),
    );
    render(<LoginPage />);

    await screen.findByText(/Sign in to FiestaBoard/i);
    expect(
      screen.queryByText(/Secure this FiestaBoard\?/i),
    ).not.toBeInTheDocument();
  });
});
