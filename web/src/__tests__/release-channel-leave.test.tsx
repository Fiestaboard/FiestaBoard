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
        channel_versions: { stable: "10.3.3", beta: "10.3.4-beta.0", alpha: "11.0.0-alpha.1" },
        can_switch: true,
        reason: null,
      }),
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
    onChannel("beta");
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    expect(await screen.findByRole("radiogroup", { name: "Release channel" })).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Beta.*Current/ })).toHaveAttribute("aria-checked", "true");
    for (const version of ["10.3.3", "10.3.4-beta.0", "11.0.0-alpha.1"])
      expect(screen.getByText(version)).toBeVisible();
  });

  it("requires a separate explicit alpha confirmation and permits cancellation", async () => {
    const posted = onChannel("stable");
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("radio", { name: /Alpha preview/ }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent(/automatic backup/i);
    expect(dialog).toHaveTextContent(/migrate/i);
    expect(posted).toHaveLength(0);
    await userEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("radio", { name: /Stable/ })).toHaveAttribute("aria-checked", "true");
    expect(posted).toHaveLength(0);
  });

  it("sends explicit major confirmation for alpha", async () => {
    const posted = onChannel("stable");
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("radio", { name: /Alpha preview/ }));
    await userEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Switch channel" }),
    );
    await waitFor(() => expect(posted).toEqual([{ channel: "alpha", confirm_major_upgrade: true }]));
  });

  it("uses the leave flow and surfaces missing backup guidance", async () => {
    const posted = onChannel("alpha", { settings_restored: false, warning: "No join snapshot was available." });
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("radio", { name: /Beta/ }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveTextContent(/restore/i);
    await userEvent.click(within(dialog).getByRole("button", { name: "Switch channel" }));
    await waitFor(() => expect(posted).toEqual([{ channel: "beta", confirm_major_upgrade: true }]));
    await waitFor(() => expect(toasts.warning).toHaveBeenCalledWith("No join snapshot was available."));
  });

  it("reports failed backup and does not start an update", async () => {
    onChannel("stable");
    server.use(
      http.post(`${API_BASE}/system/channel`, () => HttpResponse.json({ detail: "Backup failed" }, { status: 503 })),
    );
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    await userEvent.click(await screen.findByRole("radio", { name: /Alpha preview/ }));
    await userEvent.click(
      within(await screen.findByRole("alertdialog")).getByRole("button", { name: "Switch channel" }),
    );
    await waitFor(() => expect(toasts.error).toHaveBeenCalledWith(expect.stringContaining("Backup failed")));
  });

  it("explains Home Assistant management without active choices", async () => {
    server.use(
      http.get(`${API_BASE}/system/channel`, () =>
        HttpResponse.json({
          channel: "stable",
          available_channels: ["stable", "beta", "alpha"],
          can_switch: false,
          reason: "Home Assistant manages updates in the add-on store.",
          channel_versions: {},
        }),
      ),
    );
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    expect(await screen.findByText(/Home Assistant manages/)).toBeVisible();
    expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
  });
});
