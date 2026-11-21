import "fake-indexeddb/auto";

import { TooltipProvider } from "@fiestaboard/ui";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CurrentBoardProvider } from "@/components/current-board-context";
import { useAppBadge } from "@/hooks/use-app-badge";
import { ThemeProvider } from "@/hooks/use-theme";
import { readLastKnownBoard } from "@/lib/pwa/last-known-board";

import { seedLastKnownBoard } from "./helpers/last-known-board";
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
  const trigger = document.querySelector<HTMLElement>('[data-slot="sidebar-account-trigger"]')!;
  await user.click(trigger);
  return await screen.findByRole("dialog", { name: "Account menu" });
}

describe("SidebarSettingsMenu trigger", () => {
  it("allows new attention to badge after a desktop item closes More", async () => {
    const setBadge = vi.fn().mockResolvedValue(undefined);
    const clearBadge = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "setAppBadge", { configurable: true, value: setBadge });
    Object.defineProperty(navigator, "clearAppBadge", { configurable: true, value: clearBadge });
    function Menu({ attention }: { attention: string }) {
      useAppBadge(attention);
      return <SidebarSettingsMenu />;
    }
    mockAuth(SIGNED_IN);
    const user = userEvent.setup();
    const view = render(<Menu attention="update-1" />, { wrapper: TestWrapper });
    await screen.findByText("casa");
    await waitFor(() => expect(setBadge).toHaveBeenCalledOnce());
    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("button", { name: "Settings" }));
    await waitFor(() => expect(screen.queryByRole("dialog", { name: "Account menu" })).not.toBeInTheDocument());
    view.rerender(<Menu attention="update-2" />);
    await waitFor(() => expect(setBadge).toHaveBeenCalledTimes(2));
  });

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

  it("draws the signed-in user's initial as the trigger's avatar", async () => {
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });

    const trigger = await screen.findByRole("button", { name: "casa" });
    expect(trigger.querySelector('[data-slot="avatar"]')).toHaveTextContent("C");
  });

  it("falls back to More, with no avatar, when auth is off", async () => {
    mockAuth(AUTH_OFF);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });

    // There is no name to show on an install with no accounts. Not
    // "Settings": the gear beside the trigger is already called that, and
    // two neighbours with one name and different behaviour is a trap.
    const trigger = await screen.findByRole("button", { name: "More" });
    expect(screen.queryByText("casa")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Settings" })).not.toBeInTheDocument();
    // …and no monogram for a person who does not exist.
    expect(trigger.querySelector('[data-slot="avatar"]')).toBeNull();
  });

  it("keeps the name as the accessible name when the rail is collapsed", async () => {
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu collapsed />, { wrapper: TestWrapper });

    // The 64px rail renders the avatar alone, so the name has to survive as
    // a label or the control becomes an unnamed disc.
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
    await screen.findByRole("button", { name: "More" });

    const menu = await openMenu(user);
    // A header would have echoed the trigger's fallback label back at the
    // reader as if "More" were somebody's name.
    expect(within(menu).queryByText("More")).not.toBeInTheDocument();
    expect(within(menu).getAllByText("Settings")).toHaveLength(1);
  });

  // BB-FS-5 (07e `343:61586`): the header is who you are and whose hub this
  // is, not a link; Account is one row of Settings.
  it("names the owner and the hub under the username", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    server.use(http.get("/api/settings/all", () => HttpResponse.json({ general: { instance_name: "Casa FiestaPi" } })));
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");
    const popup = await openMenu(user);
    expect(await within(popup).findByText("casa · Owner of Casa FiestaPi")).toBeInTheDocument();
    expect(within(popup).queryByRole("button", { name: "Account" })).not.toBeInTheDocument();
  });

  it("puts the theme choice on one row labelled Theme, not an Appearance block", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");
    const popup = await openMenu(user);
    const group = within(popup).getByRole("radiogroup", { name: "Theme" });
    expect(
      within(group)
        .getAllByRole("radio")
        .map((radio) => radio.textContent),
    ).toEqual(["Light", "Dark", "System"]);
    expect(within(popup).queryByText("Appearance")).not.toBeInTheDocument();
  });

  it("links Help & Docs", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");
    const popup = await openMenu(user);
    expect(within(popup).getByRole("link", { name: "Help & Docs" })).toHaveAttribute(
      "href",
      "https://fiestaboard.app/docs/intro",
    );
  });

  it("opens with the keyboard and restores focus on Escape", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    const trigger = await screen.findByRole("button", { name: "casa" });
    trigger.focus();
    await user.keyboard("{Enter}");
    const popup = await screen.findByRole("dialog", { name: "Account menu" });
    expect(popup).toContainElement(document.activeElement as HTMLElement);
    await user.keyboard("{Escape}");
    await waitFor(() => expect(popup).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it("navigates to Settings", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("button", { name: "Settings" }));

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
    expect(within(menu).getByRole("radio", { name: "System" })).toBeChecked();
    expect(within(menu).getByRole("radio", { name: "Light" })).not.toBeChecked();
    expect(within(menu).getByRole("radio", { name: "Dark" })).not.toBeChecked();
  });

  it("applies Dark when Dark is chosen", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("radio", { name: "Dark" }));

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
    await user.click(within(menu).getByRole("radio", { name: "Light" }));

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
    await user.click(within(menu).getByRole("radio", { name: "System" }));

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
    await user.click(within(menu).getByRole("button", { name: "Sign out of this browser" }));

    await waitFor(() => expect(loggedOut).toBe(true));
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("wipes this account's last-known board from the device before leaving for the login page", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    server.use(http.post("/api/auth/logout", () => HttpResponse.json({ status: "ok" })));
    await seedLastKnownBoard({
      boardId: "b1",
      owner: "casa",
      message: "HELLO",
      rows: 6,
      cols: 22,
      board: null,
      savedAt: 1,
    });
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("button", { name: "Sign out of this browser" }));

    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
    expect(await readLastKnownBoard()).toBeNull();
  });

  it("hides Sign out on an install with no accounts", async () => {
    const user = userEvent.setup();
    mockAuth(AUTH_OFF);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByRole("button", { name: "More" });

    const menu = await openMenu(user);
    expect(within(menu).queryByRole("button", { name: "Sign out of this browser" })).not.toBeInTheDocument();
  });
});

describe("SidebarSettingsMenu on mobile", () => {
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
      http.get("/api/system/update/status", () =>
        HttpResponse.json({ update_available: false, managed_externally: false }),
      ),
      http.get("/api/system/update-check", () => HttpResponse.json({ update_available: false, latest_version: null })),
    );
  });

  it("renders its rows inline rather than behind a second overlay", async () => {
    render(<SidebarSettingsMenu variant="mobile" />, { wrapper: TestWrapper });

    // The drawer is already an overlay. A dropdown on top of it is two
    // dismissal layers and a 224px popup under a full-width button, which is
    // what this variant exists to avoid.
    expect(await screen.findByRole("button", { name: "Settings" })).toBeInTheDocument();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
    expect(document.querySelector('[data-slot="sidebar-account-trigger"]')).toBeNull();
  });

  it("shows the signed-in user's avatar beside their name", async () => {
    render(<SidebarSettingsMenu variant="mobile" />, { wrapper: TestWrapper });

    // The drawer has no trigger to carry the avatar, so the name row does.
    const name = await screen.findByText("casa");
    expect(name.parentElement!.querySelector('[data-slot="avatar"]')).toHaveTextContent("C");
  });

  it("switches the theme from a segmented control, with no menu to open first", async () => {
    const user = userEvent.setup();
    render(<SidebarSettingsMenu variant="mobile" />, { wrapper: TestWrapper });

    // Not a menuitemradio: inline rows are not a menu, so the three-way
    // choice can be the control it should have been all along.
    const dark = await screen.findByRole("radio", { name: "Dark" });
    await user.click(dark);

    await waitFor(() => expect(document.documentElement).toHaveClass("dark"));
    expect(localStorage.getItem("theme")).toBe("dark");
  });

  it("reaches Settings in one tap", async () => {
    const user = userEvent.setup();
    render(<SidebarSettingsMenu variant="mobile" />, { wrapper: TestWrapper });

    await user.click(await screen.findByRole("button", { name: "Settings" }));

    expect(pushMock).toHaveBeenCalledWith("/settings");
  });

  it("closes the drawer when Settings is chosen", async () => {
    // The drawer is an overlay over the route Settings pushes. Left open, it
    // hides the page the tap just went to, and the tap reads as a no-op.
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<SidebarSettingsMenu variant="mobile" onSelect={onSelect} />, { wrapper: TestWrapper });

    await user.click(await screen.findByRole("button", { name: "Settings" }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(pushMock).toHaveBeenCalledWith("/settings");
  });

  it("closes the drawer when signing out", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<SidebarSettingsMenu variant="mobile" onSelect={onSelect} />, { wrapper: TestWrapper });

    await user.click(await screen.findByRole("button", { name: "Sign out" }));

    expect(onSelect).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("leaves the drawer open behind About, which closes back onto it", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<SidebarSettingsMenu variant="mobile" onSelect={onSelect} />, { wrapper: TestWrapper });

    await user.click(await screen.findByRole("button", { name: "About FiestaBoard" }));

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it("states the running version", async () => {
    render(<SidebarSettingsMenu variant="mobile" />, { wrapper: TestWrapper });
    expect(await screen.findByText("8.38.9")).toBeInTheDocument();
  });

  it("offers About and Sign out", async () => {
    const user = userEvent.setup();
    render(<SidebarSettingsMenu variant="mobile" />, { wrapper: TestWrapper });

    expect(await screen.findByRole("button", { name: "About FiestaBoard" })).toBeInTheDocument();
    // Awaited, not fetched synchronously: About renders unconditionally and so
    // resolves as soon as the component mounts, while Sign out waits on the
    // auth query that decides whether anyone is signed in.
    await user.click(await screen.findByRole("button", { name: "Sign out" }));
    await waitFor(() => expect(replaceMock).toHaveBeenCalledWith("/login"));
  });

  it("keeps the dropdown on desktop", async () => {
    const user = userEvent.setup();
    render(<SidebarSettingsMenu variant="desktop" />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    // The desktop rail has one narrow footer slot and a working arrow-key
    // contract; only the mobile drawer changes shape.
    const menu = await openMenu(user);
    expect(within(menu).getByRole("radio", { name: "Dark" })).toBeInTheDocument();
  });
});

describe("SidebarSettingsMenu update action", () => {
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
      http.get("/api/system/update/status", () =>
        HttpResponse.json({ update_available: true, managed_externally: false }),
      ),
      http.get("/api/system/update-check", () =>
        HttpResponse.json({ update_available: true, latest_version: "8.39.0" }),
      ),
    );
  });

  it("badges About with the waiting version on desktop, and About offers the update", async () => {
    const user = userEvent.setup();
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    // 07e `343:61586`: "About FiestaBoard [Update 11.2.0]" — one row, no
    // separate "Update to" action; About's own "Update in Settings" applies it.
    const about = await within(menu).findByRole("button", { name: /About FiestaBoard.*Update 8\.39\.0/ });
    expect(within(menu).queryByRole("button", { name: /Update to/ })).not.toBeInTheDocument();
    await user.click(about);
    expect(await screen.findByRole("dialog", { name: "About FiestaBoard" })).toBeInTheDocument();
  });

  it("takes you to the updater from the mobile rows", async () => {
    const user = userEvent.setup();
    render(<SidebarSettingsMenu variant="mobile" />, { wrapper: TestWrapper });

    await user.click(await screen.findByRole("button", { name: /Update to 8\.39\.0/ }));

    expect(pushMock).toHaveBeenCalledWith("/settings");
  });

  it("closes the drawer on the way to the updater", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<SidebarSettingsMenu variant="mobile" onSelect={onSelect} />, { wrapper: TestWrapper });

    await user.click(await screen.findByRole("button", { name: /Update to 8\.39\.0/ }));

    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it("offers nothing to click when the install is current", async () => {
    let asked = false;
    server.use(
      http.get("/api/system/update/status", () => {
        asked = true;
        return HttpResponse.json({ update_available: false, managed_externally: false });
      }),
      http.get("/api/system/update-check", () => HttpResponse.json({ update_available: false, latest_version: null })),
    );
    const user = userEvent.setup();
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await waitFor(() => expect(asked).toBe(true));
    expect(within(menu).getByRole("button", { name: "About FiestaBoard" })).toBeInTheDocument();
    expect(within(menu).queryByRole("button", { name: /Update to/ })).not.toBeInTheDocument();
  });

  it("offers nothing to click when an external supervisor owns updates", async () => {
    // The Home Assistant add-on case: FiestaBoard cannot apply the update, so
    // routing someone to a button that cannot work is worse than silence.
    let asked = false;
    server.use(
      http.get("/api/system/update/status", () => {
        asked = true;
        return HttpResponse.json({ update_available: true, managed_externally: true });
      }),
    );
    const user = userEvent.setup();
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await waitFor(() => expect(asked).toBe(true));
    expect(within(menu).getByRole("button", { name: "About FiestaBoard" })).toBeInTheDocument();
    expect(within(menu).queryByRole("button", { name: /Update to/ })).not.toBeInTheDocument();
  });
});

describe("SidebarSettingsMenu trigger notice", () => {
  const trigger = () => document.querySelector<HTMLElement>('[data-slot="sidebar-account-trigger"]')!;

  beforeEach(() => {
    localStorage.clear();
    mockAuth(SIGNED_IN);
  });

  it("puts the notice it is handed on the trigger, as a dot and as words", async () => {
    render(<SidebarSettingsMenu notice="Update available" />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    // The dot alone is colour and position; the description is what a
    // screen reader hears, and it has to say the same thing.
    expect(trigger()).toHaveAccessibleDescription("Update available");
    expect(trigger().querySelector('[data-slot="sidebar-account-notice"]')).not.toBeNull();
  });

  it("draws no dot without a notice", async () => {
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    expect(trigger()).toHaveAccessibleDescription("");
    expect(trigger().querySelector('[data-slot="sidebar-account-notice"]')).toBeNull();
  });

  it("does not work out a notice of its own when an update is waiting", async () => {
    // The Sidebar owns the rule (one decision for the rail AND the mobile
    // hamburger). A second copy in here would let the two drift apart.
    server.use(
      http.get("/api/system/update/status", () =>
        HttpResponse.json({ update_available: true, managed_externally: false }),
      ),
      http.get("/api/system/update-check", () =>
        HttpResponse.json({ update_available: true, latest_version: "8.39.0" }),
      ),
    );
    const user = userEvent.setup();
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    // Wait for the update to land (the menu item proves it did) before
    // asserting the trigger stayed quiet.
    const menu = await openMenu(user);
    await within(menu).findByText("Update 8.39.0");
    expect(trigger()).toHaveAccessibleDescription("");
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

  it("leaves the build number to About rather than the menu", async () => {
    mockUpdate({ available: false });
    const user = userEvent.setup();
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    // 07e `343:61586` draws no version line; the number lives in About.
    await within(menu).findByRole("button", { name: "About FiestaBoard" });
    expect(within(menu).queryByText(/8\.38\.9/)).not.toBeInTheDocument();
  });

  it("names the waiting version once, on the About row", async () => {
    mockUpdate({ available: true });
    const user = userEvent.setup();
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await within(menu).findByText("Update 8.39.0");
    expect(within(menu).getAllByText(/8\.39\.0/)).toHaveLength(1);
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
    await user.click(within(menu).getByRole("button", { name: "About FiestaBoard" }));

    const dialog = await screen.findByRole("dialog");
    // The real number off /api/version, not a build-time constant.
    expect(await within(dialog).findByText(/FiestaBoard 8\.38\.0/)).toBeInTheDocument();
  });

  it("links to the release notes, the licenses and problem reports", async () => {
    // 07e `343:63073`: the About box's links. Documentation lives in the
    // rail's Help & Docs.
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("button", { name: "About FiestaBoard" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("link", { name: "Release notes" })).toHaveAttribute(
      "href",
      "https://github.com/Fiestaboard/FiestaBoard/releases",
    );
    expect(within(dialog).getByRole("link", { name: "Open-source licenses" })).toHaveAttribute(
      "href",
      "https://github.com/Fiestaboard/FiestaBoard/blob/main/LICENSE",
    );
    expect(within(dialog).getByRole("link", { name: "Report a problem" })).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    mockAuth(SIGNED_IN);
    render(<SidebarSettingsMenu />, { wrapper: TestWrapper });
    await screen.findByText("casa");

    const menu = await openMenu(user);
    await user.click(within(menu).getByRole("button", { name: "About FiestaBoard" }));
    await screen.findByRole("dialog");

    await user.keyboard("{Escape}");

    await waitFor(() => {
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });
  });
});
