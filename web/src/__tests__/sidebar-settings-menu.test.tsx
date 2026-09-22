import { TooltipProvider } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const pushMock = vi.fn();
const replaceMock = vi.fn();

vi.mock("@/hooks/use-router", () => ({
  useRouter: () => ({
    push: pushMock,
    replace: replaceMock,
    refresh: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/",
}));

import { SidebarSettingsMenu } from "@/components/sidebar-settings-menu";

function TestWrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <CurrentBoardProvider>
        <ThemeProvider defaultTheme="system">
          <TooltipProvider>{children}</TooltipProvider>
        </ThemeProvider>
      </CurrentBoardProvider>
    </QueryClientProvider>
  );
}

const SIGNED_IN = {
  enabled: true,
  setup_required: false,
  authenticated: true,
  username: "casa",
  mode: "enabled" as const,
  first_run: false,
};

const AUTH_OFF = {
  enabled: false,
  setup_required: false,
  authenticated: false,
  username: null,
  mode: "disabled" as const,
  first_run: false,
};

function mockAuth(payload: typeof SIGNED_IN | typeof AUTH_OFF) {
  server.use(http.get("/api/auth/status", () => HttpResponse.json(payload)));
}

/** Open the footer menu and return its popup, whatever the trigger is called. */
async function openMenu(user: ReturnType<typeof userEvent.setup>) {
  const trigger = document.querySelector<HTMLElement>('[data-slot="sidebar-settings-trigger"]')!;
  await user.click(trigger);
  return await screen.findByRole("menu");
}

describe("SidebarSettingsMenu trigger", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    localStorage.clear();
  });

  it("names the trigger after the signed-in user", async () => {
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });

    expect(await screen.findByText("casa")).toBeInTheDocument();
  });

  it("falls back to the word for settings when auth is off", async () => {
    mockAuth(AUTH_OFF);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });

    // There is no name to show on an install with no accounts, and
    // "Settings" is what is actually behind the gear.
    await waitFor(() => {
      expect(screen.getByText("Settings")).toBeInTheDocument();
    });
    expect(screen.queryByText("casa")).not.toBeInTheDocument();
  });

  it("keeps the name as the accessible name when the rail is collapsed", async () => {
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu collapsed />, { wrapper: TestWrapper });

    // The 64px rail renders the gear alone, so the name has to survive as a
    // label or the control becomes an unnamed icon.
    const trigger = await screen.findByRole("button", { name: "casa" });
    expect(trigger).toBeInTheDocument();
    expect(trigger).not.toHaveTextContent("casa");
  });
});

describe("SidebarSettingsMenu contents", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    localStorage.clear();
  });

  it("heads the menu with the signed-in username", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    expect(within(menu).getByText("casa")).toBeInTheDocument();
  });

  it("omits the username header when there is nobody signed in", async () => {
    const user = userEvent.setup();
    mockAuth(AUTH_OFF);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await waitFor(() => expect(screen.getByText("Settings")).toBeInTheDocument());

    const menu = await openMenu(user);
    // Exactly one "Settings" in the menu: the destination. A header would
    // have echoed the trigger's fallback label back at the reader.
    expect(within(menu).getAllByText("Settings")).toHaveLength(1);
  });

  it("navigates to Settings", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("menuitem", { name: "Settings" }));

    expect(pushMock).toHaveBeenCalledWith("/settings");
  });

  it("offers Light, Dark and System as one checked group", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    // The toggle this replaces had two states and the app has three; a
    // fresh install defaults to System, which the toggle could not say.
    expect(within(menu).getByRole("menuitemradio", { name: "System" })).toBeChecked();
    expect(within(menu).getByRole("menuitemradio", { name: "Light" })).not.toBeChecked();
    expect(within(menu).getByRole("menuitemradio", { name: "Dark" })).not.toBeChecked();
  });

  it("applies Dark when Dark is chosen", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("menuitemradio", { name: "Dark" }));

    await waitFor(() => {
      expect(document.documentElement).toHaveClass("dark");
    });
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("applies Light when Light is chosen", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    localStorage.setItem("theme", "dark");
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("menuitemradio", { name: "Light" }));

    await waitFor(() => {
      expect(document.documentElement).not.toHaveClass("dark");
    });
    expect(localStorage.getItem("theme")).toBe("light");
  });

  it("applies System when System is chosen", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    localStorage.setItem("theme", "dark");
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("menuitemradio", { name: "System" }));

    // jsdom's matchMedia stub reports no dark preference, so "follow the
    // system" resolves to light here — the point is that it stopped being
    // the stored "dark", not which way the system happens to lean.
    await waitFor(() => {
      expect(localStorage.getItem("theme")).toBe("system");
    });
    expect(document.documentElement).not.toHaveClass("dark");
  });

  it("signs out and returns to the login page", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    let loggedOut = false;
    server.use(
      http.post("/api/auth/logout", () => {
        loggedOut = true;
        return HttpResponse.json({ status: "ok" });
      }),
    );
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("menuitem", { name: "Sign out" }));

    await waitFor(() => expect(loggedOut).toBe(true));
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("hides Sign out on an install with no accounts", async () => {
    const user = userEvent.setup();
    mockAuth(AUTH_OFF);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await waitFor(() => expect(screen.getByText("Settings")).toBeInTheDocument());

    const menu = await openMenu(user);
    expect(within(menu).queryByRole("menuitem", { name: "Sign out" })).not.toBeInTheDocument();
  });
});

describe("SidebarSettingsMenu version row", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    localStorage.clear();
    mockAuth(SIGNED_IN);
    server.use(
      http.get("/api/version", () =>
        HttpResponse.json({
          package_version: "8.38.9",
          build_version: "8.38.9",
          running_version: "8.38.9",
          is_dev: false,
          hardware_model: null,
        }),
      ),
    );
  });

  /** An update is waiting, and this install is the one that can apply it. */
  function mockUpdate({ available, managedExternally = false }: { available: boolean; managedExternally?: boolean }) {
    server.use(
      http.get("/api/system/update/status", () =>
        HttpResponse.json({ update_available: available, managed_externally: managedExternally }),
      ),
      http.get("/api/system/update-check", () =>
        HttpResponse.json({ update_available: available, latest_version: available ? "8.39.0" : null }),
      ),
    );
  }

  it("states the running version in the menu, without opening About", async () => {
    mockUpdate({ available: false });
    const user = userEvent.setup();
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);

    // The whole point of the row: the build number without a second click.
    expect(await within(menu).findByText("8.38.9")).toBeInTheDocument();
  });

  it("marks an available update in the menu", async () => {
    mockUpdate({ available: true });
    const user = userEvent.setup();
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    const badge = await within(menu).findByTestId("settings-menu-update-badge");
    // The waiting version, and a name screen readers can read.
    expect(badge).toHaveTextContent("8.39.0");
    expect(within(badge).getByText("Update available: 8.39.0")).toBeInTheDocument();
  });

  it("shows no update marker when the install is current", async () => {
    mockUpdate({ available: false });
    const user = userEvent.setup();
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    // Anchored on the version row being rendered, so the absence is judged
    // against a row that exists rather than a menu that never loaded.
    await within(menu).findByText("8.38.9");
    expect(within(menu).queryByTestId("settings-menu-update-badge")).not.toBeInTheDocument();
  });

  it("stays quiet when an external supervisor owns updates", async () => {
    // The Home Assistant add-on case: FiestaBoard cannot apply the update,
    // so pointing at one would be an offer it cannot honour.
    mockUpdate({ available: true, managedExternally: true });
    const user = userEvent.setup();
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await within(menu).findByText("8.38.9");
    expect(within(menu).queryByTestId("settings-menu-update-badge")).not.toBeInTheDocument();
  });
});

describe("SidebarSettingsMenu About box", () => {
  beforeEach(() => {
    pushMock.mockReset();
    replaceMock.mockReset();
    localStorage.clear();
    server.use(
      http.get("/api/version", () =>
        HttpResponse.json({
          package_version: "8.38.0",
          build_version: "8.38.0",
          running_version: "8.38.0",
          is_dev: false,
          hardware_model: "Raspberry Pi 4 Model B",
        }),
      ),
    );
  });

  it("opens from the menu and shows the version the server reports", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("menuitem", { name: "About FiestaBoard" }));

    const dialog = await screen.findByRole("dialog");
    // The real number off /api/version, not a build-time constant.
    expect(await within(dialog).findByText("8.38.0")).toBeInTheDocument();
  });

  it("shows the hardware the server reports", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("menuitem", { name: "About FiestaBoard" }));

    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Raspberry Pi 4 Model B")).toBeInTheDocument();
  });

  it("states the licence", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("menuitem", { name: "About FiestaBoard" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("MIT License")).toBeInTheDocument();
    expect(within(dialog).getByText("© 2026 Fiestaboard contributors")).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("menuitem", { name: "About FiestaBoard" }));
    await screen.findByRole("dialog");

    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });

  it("omits the hardware row when the server does not know the model", async () => {
    // A Docker install on a generic host reports null, and "Hardware:
    // Unknown" is worse than no row at all.
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    server.use(
      http.get("/api/version", () =>
        HttpResponse.json({
          package_version: "8.38.0",
          build_version: "8.38.0",
          running_version: "8.38.0",
          is_dev: false,
          hardware_model: null,
        }),
      ),
    );
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("menuitem", { name: "About FiestaBoard" }));

    const dialog = await screen.findByRole("dialog");
    await within(dialog).findByText("8.38.0");
    expect(within(dialog).queryByText("Hardware")).not.toBeInTheDocument();
  });
});
