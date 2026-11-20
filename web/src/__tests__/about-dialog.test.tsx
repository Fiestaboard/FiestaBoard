/**
 * BB-C-11: About said "Channel: Stable" on an alpha build (any channel that
 * was not "beta" read as Stable), and on a phone it was a square centred
 * modal. Figma `343:63073` (dialog) / `343:64171` (phone sheet): "This page"
 * and "Hub" versions, the release channel, the update state.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AboutDialog } from "@/components/about-dialog";

import pkg from "../../package.json";
import { server } from "./mocks/server";

function renderAbout() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <AboutDialog open onOpenChange={() => {}} />
    </QueryClientProvider>,
  );
}

function phoneWidth(phone: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: phone && query === "(max-width: 767.98px)",
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }));
}

beforeEach(() => {
  server.use(
    http.get("*/api/version", () =>
      HttpResponse.json({
        package_version: "11.0.0-alpha.10",
        build_version: "dev",
        running_version: "11.0.0-alpha.10",
        is_dev: true,
        hardware_model: null,
      }),
    ),
    http.get("*/api/system/channel", () =>
      HttpResponse.json({
        channel: "alpha",
        running_channel: "alpha",
        running_version: "11.0.0-alpha.10",
        available_channels: ["alpha", "beta", "stable"],
        can_switch: false,
        reason: null,
      }),
    ),
  );
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("AboutDialog (BB-C-11)", () => {
  it("names the alpha channel on an alpha build, not Stable", async () => {
    phoneWidth(false);
    renderAbout();
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Alpha preview")).toBeInTheDocument();
    expect(within(dialog).queryByText("Stable")).not.toBeInTheDocument();
  });

  it("states this page's version and the hub's version", async () => {
    phoneWidth(false);
    renderAbout();
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("This page")).toBeInTheDocument();
    expect(within(dialog).getByText(`FiestaBoard web ${pkg.version}`)).toBeInTheDocument();
    expect(within(dialog).getByText("Hub")).toBeInTheDocument();
    expect(await within(dialog).findByText(/FiestaBoard 11\.0\.0-alpha\.10/)).toBeInTheDocument();
    expect(within(dialog).queryByText(/dev build/)).not.toBeInTheDocument();
  });

  it("offers the waiting update with a way to Settings", async () => {
    phoneWidth(false);
    server.use(
      http.get("*/api/system/update-check", () =>
        HttpResponse.json({
          current_version: "11.0.0-alpha.10",
          latest_version: "11.0.0-alpha.11",
          update_available: true,
          package_url: "",
          error: null,
          is_production: true,
        }),
      ),
    );
    renderAbout();
    const dialog = await screen.findByRole("dialog");
    expect(await within(dialog).findByText("Update available")).toBeInTheDocument();
    expect(within(dialog).getByText("FiestaBoard 11.0.0-alpha.11")).toBeInTheDocument();
    expect(within(dialog).getByRole("link", { name: "Update in Settings" })).toHaveAttribute(
      "href",
      "/settings/system",
    );
  });

  it("is a bottom sheet on a phone", async () => {
    phoneWidth(true);
    renderAbout();
    const sheet = await screen.findByRole("dialog");
    expect(sheet).toHaveAttribute("data-slot", "sheet-content");
    expect(sheet).toHaveAttribute("data-side", "bottom");
  });

  it("is a centred dialog from the rail up", async () => {
    phoneWidth(false);
    renderAbout();
    expect(await screen.findByRole("dialog")).toHaveAttribute("data-slot", "dialog-content");
  });
});
