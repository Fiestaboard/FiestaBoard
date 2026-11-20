/**
 * Leaving the beta from the Release channel card.
 *
 * The card shipped join-only: its button rendered solely when the box was on
 * stable, so a FiestaPi that opted in had no way back from the UI at all --
 * the API accepted a switch to stable and nothing called it.
 *
 * These cover the half that was missing, and the one thing about it that is
 * genuinely dangerous: leaving before the release catches up is a downgrade
 * across a major, and if the join snapshot could not be restored the stable
 * build may come up on data it refuses to read. The server says so in
 * `warning`; the card has to show it rather than report a silent success.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ReleaseChannelCard } from "@/components/settings/release-channel";
import { UpdateProvider } from "@/components/update-context";
import { ThemeProvider } from "@/hooks/use-theme";

import { server } from "./mocks/server";

const API_BASE = "/api";

const toasts = vi.hoisted(() => ({ warning: vi.fn(), error: vi.fn(), success: vi.fn() }));
vi.mock("sonner", () => ({ toast: toasts }));

function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="light">
        <UpdateProvider>{children}</UpdateProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

/** Put the card on a channel, and capture what a switch would POST. */
function onChannel(channel: "stable" | "beta" | "alpha", switchResponse: Record<string, unknown> = {}) {
  const posted: Array<Record<string, unknown>> = [];
  server.use(
    http.get(`${API_BASE}/system/channel`, () =>
      HttpResponse.json({
        channel,
        available_channels: ["stable", "beta", "alpha"],
        running_channel: channel,
        running_version: channel === "alpha" ? "11.0.0-alpha.0" : "10.3.3",
        channel_versions: { stable: "10.3.3", beta: "10.3.4-beta.0", alpha: "11.0.0-alpha.1" },
        can_switch: true,
        reason: null,
      }),
    ),
    http.get(`${API_BASE}/system/channel/versions`, () =>
      HttpResponse.json({ channel_versions: { stable: "10.3.3", beta: "10.3.4-beta.0", alpha: "11.0.0-alpha.1" } }),
    ),
    http.post(`${API_BASE}/system/channel`, async ({ request }) => {
      posted.push((await request.json()) as Record<string, unknown>);
      return HttpResponse.json({
        status: "queued",
        channel: channel === "beta" ? "stable" : "beta",
        tag: channel === "beta" ? "latest" : "beta",
        settings_snapshot: null,
        ...switchResponse,
      });
    }),
  );
  return posted;
}

beforeEach(() => {
  toasts.warning.mockClear();
  toasts.error.mockClear();
});

describe("ReleaseChannelCard", () => {
  it("shows all versions and the running channel", async () => {
    onChannel("alpha");
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    expect(await screen.findByRole("radiogroup", { name: "Release channel" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Alpha preview.*Current/ })).toHaveAttribute("aria-checked", "true");
    // The current channel shows what is running; the others what they publish.
    for (const version of ["10.3.3", "10.3.4-beta.0", "11.0.0-alpha.0"])
      expect(await screen.findByText(version)).toBeVisible();
  });

  // BB-C-13: Figma 320:8881's Version card — the running version and whether
  // it is current, above the channel choice.
  it("states the running version and that it is up to date", async () => {
    onChannel("stable");
    server.use(
      http.get(`${API_BASE}/system/update-check`, () =>
        HttpResponse.json({
          current_version: "10.3.3",
          latest_version: "10.3.3",
          update_available: false,
          package_url: "",
          error: null,
          is_production: true,
        }),
      ),
    );
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    expect(await screen.findByText("FiestaBoard 10.3.3 · Up to date")).toBeVisible();
  });

  it("draws version numbers as written, not as uppercase code", async () => {
    onChannel("alpha");
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    const version = await screen.findByText("11.0.0-alpha.0");
    expect(version.closest(".uppercase")).toBeNull();
  });

  it("names the real backup section when leaving a preview", async () => {
    onChannel("alpha");
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("radio", { name: /Stable/ }));
    await userEvent.click(screen.getByRole("button", { name: "Switch channel" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent("System & backups › Backup & Restore");
    expect(dialog).not.toHaveTextContent("System → Backup");
  });

  it("never shows the server's setup instructions to the user", async () => {
    server.use(
      http.get(`${API_BASE}/system/channel`, () =>
        HttpResponse.json({
          channel: "stable",
          running_channel: "stable",
          running_version: "10.3.3",
          available_channels: ["stable", "beta", "alpha"],
          can_switch: false,
          reason:
            "The updater sidecar is not enabled. Add COMPOSE_PROFILES=fiestaupdater to your .env and run 'docker compose up -d'.",
        }),
      ),
    );
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    expect(await screen.findByText("Channel switching is unavailable on this install.")).toBeVisible();
    expect(screen.queryByText(/COMPOSE_PROFILES|sidecar/)).not.toBeInTheDocument();
  });

  it("requires a separate explicit alpha confirmation and permits cancellation", async () => {
    const posted = onChannel("stable");
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("radio", { name: /Alpha preview/ }));
    await userEvent.click(screen.getByRole("button", { name: "Switch channel" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent(/automatic backup/i);
    expect(dialog).toHaveTextContent(/migrate/i);
    expect(posted).toHaveLength(0);
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("radio", { name: /Alpha preview/ })).toHaveAttribute("aria-checked", "true");
    expect(screen.getByRole("radio", { name: /Stable.*Current/ })).toBeInTheDocument();
    expect(posted).toHaveLength(0);
  });

  it("sends explicit major confirmation for alpha", async () => {
    const posted = onChannel("stable");
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("radio", { name: /Alpha preview/ }));
    await userEvent.click(screen.getByRole("button", { name: "Switch channel" }));
    await userEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Switch channel" }),
    );
    await waitFor(() => expect(posted).toEqual([{ channel: "alpha", confirm_major_upgrade: true }]));
  });

  it("uses the leave flow and surfaces missing backup guidance", async () => {
    const posted = onChannel("alpha", { settings_restored: false, warning: "No join snapshot was available." });
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("radio", { name: /Beta/ }));
    await userEvent.click(screen.getByRole("button", { name: "Switch channel" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent(/restore/i);
    await userEvent.click(within(dialog).getByRole("button", { name: "Switch channel" }));
    await waitFor(() => expect(posted).toEqual([{ channel: "beta", confirm_major_upgrade: false }]));
    await waitFor(() => expect(toasts.warning).toHaveBeenCalledWith("No join snapshot was available."));
  });

  it("reports failed backup and does not start an update", async () => {
    onChannel("stable");
    server.use(
      http.post(`${API_BASE}/system/channel`, () => HttpResponse.json({ detail: "Backup failed" }, { status: 503 })),
    );
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("radio", { name: /Alpha preview/ }));
    await userEvent.click(screen.getByRole("button", { name: "Switch channel" }));
    await userEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Switch channel" }),
    );
    await waitFor(() => expect(toasts.error).toHaveBeenCalledWith(expect.stringContaining("Backup failed")));
  });

  it.each(["{Enter}", " "])("arrow keys only explore; %s opens explicit confirmation", async (activation) => {
    const posted = onChannel("stable");
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    const stable = await screen.findByRole("radio", { name: /Stable/ });
    stable.focus();
    await userEvent.keyboard("{ArrowDown}");
    const beta = screen.getByRole("radio", { name: /Beta/ });
    expect(beta).toHaveFocus();
    expect(beta).toHaveAttribute("aria-checked", "true");
    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument();
    expect(posted).toHaveLength(0);
    await userEvent.keyboard(activation);
    expect(await screen.findByRole("alertdialog")).toBeVisible();
    expect(posted).toHaveLength(0);
  });

  it("renders the running channel while discovery is pending, then unavailable rows on failure", async () => {
    onChannel("beta");
    let release!: () => void;
    const pending = new Promise<void>((resolve) => {
      release = resolve;
    });
    server.use(
      http.get(`${API_BASE}/system/channel/versions`, async () => {
        await pending;
        return HttpResponse.json({ detail: "Offline" }, { status: 503 });
      }),
    );
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    try {
      expect(await screen.findByRole("radio", { name: /Beta.*Current/ })).toBeVisible();
      // The running channel's version is known locally; only the others wait.
      expect(screen.getAllByText("Loading version…")).toHaveLength(2);
    } finally {
      release();
    }
    await waitFor(() => expect(screen.getAllByText("Version unavailable")).toHaveLength(2));
    expect(screen.getByText("10.3.3")).toBeVisible();
  });

  it.each([
    ["stable", "beta", false],
    ["alpha", "beta", false],
    ["alpha", "stable", false],
    ["beta", "alpha", true],
  ] as const)("confirms major upgrade precisely for %s to %s", async (running, candidate, expected) => {
    const posted = onChannel(running);
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    // Discovery settled (the running channel's row shows its own version).
    await screen.findByRole("radiogroup");
    await waitFor(() => expect(screen.queryByText("Loading version…")).not.toBeInTheDocument());
    await userEvent.click(
      screen.getByRole("radio", {
        name: candidate === "stable" ? /Stable/ : candidate === "beta" ? /Beta/ : /Alpha preview/,
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Switch channel" }));
    await userEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Switch channel" }),
    );
    await waitFor(() => expect(posted).toEqual([{ channel: candidate, confirm_major_upgrade: expected }]));
  });

  it("does not confirm an alpha major upgrade from an already running 11.x stable build", async () => {
    const posted = onChannel("stable");
    server.use(
      http.get(`${API_BASE}/system/channel`, () =>
        HttpResponse.json({
          channel: "stable",
          running_channel: "stable",
          running_version: "11.0.0",
          available_channels: ["stable", "beta", "alpha"],
          can_switch: true,
          reason: null,
        }),
      ),
    );
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("radio", { name: /Alpha preview/ }));
    await userEvent.click(screen.getByRole("button", { name: "Switch channel" }));
    await userEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Switch channel" }),
    );
    await waitFor(() => expect(posted).toEqual([{ channel: "alpha", confirm_major_upgrade: false }]));
  });

  it("explains Home Assistant management without active choices", async () => {
    server.use(
      http.get(`${API_BASE}/system/channel`, () =>
        HttpResponse.json({
          channel: "stable",
          available_channels: ["stable", "beta", "alpha"],
          can_switch: false,
          reason: "This install is managed by Home Assistant.",
          channel_versions: {},
        }),
      ),
      http.get(`${API_BASE}/system/update/status`, () =>
        HttpResponse.json({
          updater_available: false,
          auto_update_enabled: false,
          auto_update_interval: "weekly",
          managed_externally: true,
          profile: null,
        }),
      ),
    );
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    expect(await screen.findByText(/Home Assistant manages/)).toBeVisible();
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
  });
});
