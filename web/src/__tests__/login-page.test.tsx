import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

function makeStatus(
  overrides: Partial<{
    enabled: boolean;
    setup_required: boolean;
    authenticated: boolean;
    username: string | null;
    mode: "enabled" | "disabled" | "undecided";
    first_run: boolean;
  }>,
) {
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
        HttpResponse.json(makeStatus({ mode: "undecided", first_run: true, setup_required: true })),
      ),
    );
    render(<LoginPage />);

    await screen.findByText(/Protect this FiestaBoard\?/i);
    expect(screen.getByRole("button", { name: /Set up a username/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Skip — anyone on my network/i })).toBeInTheDocument();
  });

  it("clicking 'Set up a username & password' switches to the setup form", async () => {
    server.use(
      http.get("/api/auth/status", () =>
        HttpResponse.json(makeStatus({ mode: "undecided", first_run: true, setup_required: true })),
      ),
    );
    render(<LoginPage />);

    await screen.findByText(/Protect this FiestaBoard\?/i);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Set up a username/i }));

    await screen.findByText(/Create administrator/i);
  });

  it("clicking 'Skip' POSTs preference and redirects", async () => {
    let body: { enabled?: boolean } | null = null;
    server.use(
      http.get("/api/auth/status", () =>
        HttpResponse.json(makeStatus({ mode: "undecided", first_run: true, setup_required: true })),
      ),
      http.post("/api/auth/preference", async ({ request }) => {
        body = (await request.json()) as { enabled?: boolean };
        return HttpResponse.json({ status: "ok" });
      }),
    );
    render(<LoginPage />);

    await screen.findByText(/Protect this FiestaBoard\?/i);
    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /Skip — anyone on my network/i }));

    await waitFor(() => {
      expect(body).toEqual({ enabled: false });
    });
    expect(replaceMock).toHaveBeenCalledWith("/");
  });

  it("renders the sign-in form for an existing user (no first_run)", async () => {
    server.use(
      http.get("/api/auth/status", () =>
        HttpResponse.json(makeStatus({ mode: "enabled", first_run: false, setup_required: false })),
      ),
    );
    render(<LoginPage />);

    await screen.findByText(/Sign in to FiestaBoard/i);
    expect(screen.queryByText(/Protect this FiestaBoard\?/i)).not.toBeInTheDocument();
  });
});

describe("LoginPage 'Keep me logged in'", () => {
  beforeEach(() => {
    replaceMock.mockReset();
  });

  function mockSignInStatus() {
    server.use(
      http.get("/api/auth/status", () =>
        HttpResponse.json(makeStatus({ mode: "enabled", first_run: false, setup_required: false })),
      ),
    );
  }

  /** Wire up the login route and capture its JSON body. */
  function captureLoginBody(): () => Record<string, unknown> | null {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post("/api/auth/login", async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ status: "ok", username: "admin" });
      }),
    );
    return () => body;
  }

  it("shows the checkbox checked by default on the sign-in form", async () => {
    mockSignInStatus();
    render(<LoginPage />);

    await screen.findByText(/Sign in to FiestaBoard/i);
    const checkbox = screen.getByRole("checkbox", { name: /Keep me logged in/i });
    expect(checkbox).toBeInTheDocument();
    expect(checkbox).toBeChecked();
  });

  it("submits remember_me=true when the box is left checked", async () => {
    mockSignInStatus();
    const getBody = captureLoginBody();
    render(<LoginPage />);

    await screen.findByText(/Sign in to FiestaBoard/i);
    const user = userEvent.setup();
    await user.type(screen.getByLabelText(/Username/i), "admin");
    await user.type(screen.getByLabelText(/Password/i), "supersecret");
    await user.click(screen.getByRole("button", { name: /Sign in/i }));

    await waitFor(() => {
      expect(getBody()).toEqual({
        username: "admin",
        password: "supersecret",
        remember_me: true,
      });
    });
  });

  it("submits remember_me=false when the box is unchecked", async () => {
    mockSignInStatus();
    const getBody = captureLoginBody();
    render(<LoginPage />);

    await screen.findByText(/Sign in to FiestaBoard/i);
    const user = userEvent.setup();
    await user.click(screen.getByRole("checkbox", { name: /Keep me logged in/i }));
    await user.type(screen.getByLabelText(/Username/i), "admin");
    await user.type(screen.getByLabelText(/Password/i), "supersecret");
    await user.click(screen.getByRole("button", { name: /Sign in/i }));

    await waitFor(() => {
      expect(getBody()).toEqual({
        username: "admin",
        password: "supersecret",
        remember_me: false,
      });
    });
  });
});
