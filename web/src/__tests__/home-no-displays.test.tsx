import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import Home from "../../app/routes/home";
import { server } from "./mocks/server";

const triggerWizard = vi.fn();
vi.mock("@/components/wizard-provider", () => ({ useWizard: () => ({ triggerWizard }) }));
vi.mock("@/hooks/use-router", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/components/active-page-display", () => ({ ActivePageDisplay: () => <section aria-label="Active board" /> }));
vi.mock("@/components/home/home-compose", () => ({ HomeCompose: () => null }));
vi.mock("@/components/status-banners/status-banner-host", () => ({ StatusBannerHost: () => null }));

function asPhone(phone: boolean) {
  vi.spyOn(window, "matchMedia").mockImplementation(
    (query: string) =>
      ({
        matches: phone && query.includes("max-width"),
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }) as unknown as MediaQueryList,
  );
}

function renderHome(placeholder = false, hubName: string | null = null) {
  server.use(
    http.get("/api/settings/all", () => HttpResponse.json({ general: { instance_name: hubName ?? "" } })),
    http.get("/api/settings/board", () =>
      HttpResponse.json({
        boards: placeholder
          ? [{ id: "default", name: "My Board", device_type: "flagship", output: "vestaboard", output_config: {} }]
          : [],
      }),
    ),
    http.get("/api/config/validate", () =>
      HttpResponse.json({ valid: false, is_first_run: false, errors: [], missing_fields: [] }),
    ),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <Home />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  triggerWizard.mockClear();
  vi.restoreAllMocks();
});

describe("Home without displays", () => {
  it("replaces the active board with a useful empty state after setup is skipped", async () => {
    renderHome();
    expect(await screen.findByRole("region", { name: "Nothing to show on yet" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Active board" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add display" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Run setup again" })).toBeInTheDocument();
  });
  it("treats an untouched seed placeholder as no display", async () => {
    renderHome(true);
    expect(await screen.findByRole("region", { name: "Nothing to show on yet" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Active board" })).not.toBeInTheDocument();
  });
  it("opens the two-step Add display dialog without opening the wizard", async () => {
    renderHome();
    await userEvent.click(await screen.findByRole("button", { name: "Add display" }));
    expect(await screen.findByRole("dialog", { name: "Add a display" })).toBeInTheDocument();
    expect(screen.getByText("Step 1 of 2 · What do you want FiestaBoard to show on?")).toBeInTheDocument();
    expect(triggerWizard).not.toHaveBeenCalled();
  });
  it("opens the wizard only from Run setup again", async () => {
    renderHome();
    await userEvent.click(await screen.findByRole("button", { name: "Run setup again" }));
    await waitFor(() => expect(triggerWizard).toHaveBeenCalledOnce());
  });
});

// BB-FH-10: 07e `343:65200` (1440), `347:65842` (900), `343:66216` (390).
describe("Home without displays matches 07e", () => {
  it("titles the state in semibold and names the hub that is running", async () => {
    renderHome(false, "Maya’s FiestaPi");
    const region = await screen.findByRole("region", { name: "Nothing to show on yet" });
    // The kit's EmptyState title is medium; 07e draws it semibold.
    expect(region.className).toContain("[&_h3]:font-semibold");
    expect(
      await screen.findByText(
        "Maya’s FiestaPi is running, but no display is connected. Add your Vestaboard, a TV or an LED display and Home will show what’s on it.",
      ),
    ).toBeInTheDocument();
  });

  it("says the pages can wait, under the actions", async () => {
    renderHome();
    const footnote = await screen.findByText(
      "You can still make pages now; they wait in Pages until a display is added.",
    );
    const add = screen.getByRole("button", { name: "Add display" });
    expect(add.compareDocumentPosition(footnote) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("falls back to “Your hub” when the hub has no name", async () => {
    renderHome();
    expect(await screen.findByText(/^Your hub is running, but no display is connected\./)).toBeInTheDocument();
  });

  it("on a phone keeps the first sentence only, no footnote, and a bare Home header", async () => {
    asPhone(true);
    renderHome(false, "Maya’s FiestaPi");
    expect(await screen.findByText("Maya’s FiestaPi is running, but no display is connected.")).toBeInTheDocument();
    expect(screen.queryByText(/until a display is added/)).toBeNull();
    expect(screen.queryByText("What’s on your displays right now, and what’s next.")).toBeNull();
    expect(screen.getByRole("heading", { level: 1, name: "Home" })).toBeInTheDocument();
  });
});

// BB-FH-9 (07a `306:53086`): a phone's Home subtitle is the one-line
// "What’s on your displays now"; wider screens keep the long sentence.
describe("Home subtitle", () => {
  function renderWithDisplay() {
    server.use(
      http.get("/api/settings/board", () =>
        HttpResponse.json({
          boards: [
            {
              id: "k",
              name: "Kitchen",
              device_type: "flagship",
              output: "vestaboard",
              output_config: { host: "192.0.2.1" },
            },
          ],
        }),
      ),
    );
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <Home />
      </QueryClientProvider>,
    );
  }

  it("is the short line on a phone", async () => {
    asPhone(true);
    renderWithDisplay();
    expect(await screen.findByText("What’s on your displays now")).toBeInTheDocument();
    expect(screen.queryByText("What’s on your displays right now, and what’s next.")).toBeNull();
  });

  it("keeps the long sentence on wider screens", async () => {
    asPhone(false);
    renderWithDisplay();
    expect(await screen.findByText("What’s on your displays right now, and what’s next.")).toBeInTheDocument();
  });
});
