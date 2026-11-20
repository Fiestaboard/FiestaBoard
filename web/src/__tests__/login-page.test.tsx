import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { server } from "./mocks/server";

const replaceMock = vi.fn();
// Module-level so useRouter() returns the SAME object every call —
// otherwise LoginPage's `useEffect([router, ...])` (page.tsx:107-131)
// sees a fresh `router` reference on every render, re-fires its
// fetchAuthStatus chain, setState triggers another render, and the
// component loops indefinitely under jsdom. The pre-migration shape
// returned a stable router from Next.js itself; this mock just had
// to be re-stabilized for the RR7 compat shim path.
const stableRouter = {
  push: vi.fn(),
  replace: replaceMock,
  refresh: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  prefetch: vi.fn(),
};
const stableSearchParams = new URLSearchParams("");

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => stableRouter,
  useSearchParams: () => stableSearchParams,
  usePathname: () => "/login",
}));

import LoginPage from "../../app/routes/login";

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

  it("keeps the wordmark without a second taco while checking authentication", () => {
    server.use(http.get("/api/auth/status", () => new Promise(() => {})));
    const { container } = render(<LoginPage />);
    expect(container.querySelector('[data-slot="spinner"]')).toBeInTheDocument();
    expect(container.querySelector('svg[viewBox="0 0 32 32"]')).not.toBeInTheDocument();
    expect(screen.getByText("Fiesta")).toBeInTheDocument();
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

describe("LoginPage 'Keep me signed in on this browser'", () => {
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
    const checkbox = screen.getByRole("checkbox", { name: /Keep me signed in on this browser/i });
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
    await user.click(screen.getByRole("checkbox", { name: /Keep me signed in on this browser/i }));
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

it("rejects an external post-login redirect", async () => {
  replaceMock.mockReset();
  stableSearchParams.set("redirect", "//attacker.invalid");
  server.use(http.get("/api/auth/status", () => HttpResponse.json(makeStatus({ authenticated: true }))));
  render(<LoginPage />);
  await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/"));
  stableSearchParams.delete("redirect");
});

describe("LoginPage sign-in form (07e Sign in `326:40175` / `326:34407`)", () => {
  beforeEach(() => {
    replaceMock.mockReset();
    server.use(
      http.get("/api/auth/status", () =>
        HttpResponse.json(makeStatus({ mode: "enabled", first_run: false, setup_required: false })),
      ),
    );
  });

  it("names the hub this browser reached and that it answered (BB-C-9)", async () => {
    const { container } = render(<LoginPage />);
    await screen.findByRole("heading", { level: 1, name: /Sign in to FiestaBoard/i });
    const line = container.querySelector('[data-slot="login-hub-line"]');
    expect(line).toHaveTextContent(`${window.location.hostname} · Online`);
    // No generic "administrator credentials" blurb under the title.
    expect(screen.queryByText(/administrator credentials/i)).not.toBeInTheDocument();
  });

  it("lets the reader reveal the password (BB-C-9)", async () => {
    render(<LoginPage />);
    const password = await screen.findByLabelText(/^Password$/i);
    expect(password).toHaveAttribute("type", "password");
    await userEvent.setup().click(screen.getByRole("button", { name: /^Show$/i }));
    expect(password).toHaveAttribute("type", "text");
  });

  it("links a forgotten password to the reset page (BB-C-9)", async () => {
    render(<LoginPage />);
    await screen.findByText(/Forgot your password\?/i);
    const link = screen.getByRole("link", { name: /Reset it with a code from the hub/i });
    expect(link).toHaveAttribute("href", "/reset-password");
  });

  it("has no 'change this later' footer on the sign-in form (BB-C-10)", async () => {
    render(<LoginPage />);
    await screen.findByLabelText(/^Password$/i);
    expect(screen.queryByText(/change this later/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /authentication docs/i })).not.toBeInTheDocument();
  });

  it("on a wrong password explains it, clears the password and puts focus there (BB-C-9)", async () => {
    server.use(
      http.post("/api/auth/login", () =>
        HttpResponse.json({ detail: "Invalid username or password" }, { status: 401 }),
      ),
    );
    render(<LoginPage />);
    const user = userEvent.setup();
    const username = await screen.findByLabelText(/Username/i);
    const password = screen.getByLabelText(/^Password$/i);
    await user.type(username, "maya");
    await user.type(password, "wrong-password");
    await user.click(screen.getByRole("button", { name: /^Sign in$/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/That username and password don.t match/i);
    expect(alert).toHaveTextContent(/Check caps lock and try again/i);
    expect(username).toHaveValue("maya");
    expect(password).toHaveValue("");
    expect(password).toHaveAttribute("aria-invalid", "true");
    expect(password).toHaveAttribute("aria-describedby", alert.id);
    await waitFor(() => expect(password).toHaveFocus());

    // The retry: typing stays in the password field, the explanation stays up.
    await user.keyboard("abc");
    expect(password).toHaveValue("abc");
    expect(username).toHaveValue("maya");
    expect(password).toHaveFocus();
    expect(screen.getByRole("alert")).toHaveTextContent(/Check caps lock and try again/i);
  });
});

it("keeps the docs footnote as one sentence on the first-run picker (BB-C-10)", async () => {
  server.use(
    http.get("/api/auth/status", () =>
      HttpResponse.json(makeStatus({ mode: "undecided", first_run: true, setup_required: true })),
    ),
  );
  render(<LoginPage />);
  const link = await screen.findByRole("link", { name: /authentication docs/i });
  // One paragraph holds the whole sentence, so it wraps as text instead of
  // splitting into flex columns.
  const sentence = link.closest("p");
  expect(sentence).not.toBeNull();
  expect(sentence).toHaveTextContent(/You can change this later — see the authentication docs/);
  expect(sentence?.textContent?.trim().endsWith(".")).toBe(true);
});
