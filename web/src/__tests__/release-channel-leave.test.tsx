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
import { render, screen, waitFor } from "@testing-library/react";
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
function onChannel(channel: "stable" | "beta", switchResponse: Record<string, unknown> = {}) {
  const posted: Array<Record<string, unknown>> = [];
  server.use(
    http.get(`${API_BASE}/system/channel`, () =>
      HttpResponse.json({
        channel,
        available_channels: ["beta", "stable"],
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
  it("offers a way off the beta when the box is on one", async () => {
    onChannel("beta");
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    expect(await screen.findByRole("button", { name: /leave the beta/i })).toBeInTheDocument();
  });

  it("still offers joining when the box is on stable", async () => {
    onChannel("stable");
    render(<ReleaseChannelCard />, { wrapper: Wrapper });
    expect(await screen.findByRole("button", { name: /join the beta/i })).toBeInTheDocument();
  });

  it("asks the server for stable when leaving", async () => {
    const posted = onChannel("beta");
    render(<ReleaseChannelCard />, { wrapper: Wrapper });

    await userEvent.click(await screen.findByRole("button", { name: /leave the beta/i }));
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within_(dialog, /leave the beta/i));

    await waitFor(() => expect(posted).toHaveLength(1));
    expect(posted[0]).toEqual({ channel: "stable" });
  });

  it("warns when the settings could not be rolled back", async () => {
    // The dangerous outcome: the box moves to an older major and the config
    // it needs was never restored. Reporting plain success hides that.
    onChannel("beta", { settings_restored: false, warning: "No join snapshot was available." });
    render(<ReleaseChannelCard />, { wrapper: Wrapper });

    await userEvent.click(await screen.findByRole("button", { name: /leave the beta/i }));
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within_(dialog, /leave the beta/i));

    await waitFor(() => expect(toasts.warning).toHaveBeenCalledWith("No join snapshot was available."));
  });

  it("stays quiet when the rollback worked", async () => {
    onChannel("beta", { settings_restored: true, warning: null });
    render(<ReleaseChannelCard />, { wrapper: Wrapper });

    await userEvent.click(await screen.findByRole("button", { name: /leave the beta/i }));
    const dialog = await screen.findByRole("alertdialog");
    await userEvent.click(within_(dialog, /leave the beta/i));

    await waitFor(() => expect(toasts.warning).not.toHaveBeenCalled());
  });
});

/** The confirm button inside the dialog, not the card button that opened it. */
function within_(scope: HTMLElement, name: RegExp): HTMLElement {
  const match = Array.from(scope.querySelectorAll("button")).find((b) => name.test(b.textContent ?? ""));
  if (!match) throw new Error(`no button matching ${name} inside the dialog`);
  return match;
}
