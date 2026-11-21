import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import React from "react";
import { afterEach, describe, expect, it } from "vitest";

import { HomeColorStrip } from "@/components/home/home-color-strip";
import { AnimationSettings } from "@/components/settings/animation-settings";
import { AppearanceSettings } from "@/components/settings/appearance-settings";
import { ConfigOverridesProvider } from "@/hooks/use-config-overrides";
import { HOME_COLOR_STRIP_KEY } from "@/hooks/use-home-color-strip";
import { ThemeProvider } from "@/hooks/use-theme";

import { mockDisplaySettings } from "./mocks/handlers";
import { server } from "./mocks/server";

// BB-FC-12: 07e Appearance (`333:56102`) draws a "Boards" card with two
// switches; the hub's finer motion settings move to a Motion details panel.

function Wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return (
    <QueryClientProvider client={queryClient}>
      <ConfigOverridesProvider>
        <ThemeProvider attribute="class" defaultTheme="light">
          {children}
        </ThemeProvider>
      </ConfigOverridesProvider>
    </QueryClientProvider>
  );
}

function withDisplay(overrides: Partial<typeof mockDisplaySettings>) {
  const bodies: Record<string, unknown>[] = [];
  server.use(
    http.get("/api/settings/all", () => HttpResponse.json({ display: { ...mockDisplaySettings, ...overrides } })),
    http.put("/api/settings/display", async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      bodies.push(body);
      return HttpResponse.json({ status: "success", settings: { ...mockDisplaySettings, ...overrides, ...body } });
    }),
  );
  return bodies;
}

afterEach(() => localStorage.removeItem(HOME_COLOR_STRIP_KEY));

describe("Appearance › Boards", () => {
  it("draws the two 07e switches under a Boards heading", async () => {
    withDisplay({ board_animations: "on" });
    render(<AppearanceSettings />, { wrapper: Wrapper });
    expect(screen.getByText("Boards")).toBeInTheDocument();
    const flips = screen.getByRole("switch", { name: "Animate tile flips" });
    expect(flips).toHaveAccessibleDescription("Board previews flip like the real board.");
    await waitFor(() => expect(flips).toBeChecked());
    expect(screen.getByRole("switch", { name: "Show the color strip on Home" })).toBeChecked();
  });

  it("turns board animations off and on for the hub with Animate tile flips", async () => {
    const bodies = withDisplay({ board_animations: "on" });
    render(<AppearanceSettings />, { wrapper: Wrapper });
    const flips = screen.getByRole("switch", { name: "Animate tile flips" });
    await waitFor(() => expect(flips).toBeEnabled());
    await userEvent.click(flips);
    await waitFor(() => expect(bodies).toEqual([{ board_animations: "off" }]));
  });

  it("reads a desktop-only hub as animating", async () => {
    withDisplay({ board_animations: "desktop" });
    render(<AppearanceSettings />, { wrapper: Wrapper });
    const flips = screen.getByRole("switch", { name: "Animate tile flips" });
    await waitFor(() => expect(flips).toBeEnabled());
    expect(flips).toBeChecked();
  });

  it("remembers the colour strip choice in this browser, not on the hub", async () => {
    const bodies = withDisplay({});
    render(<AppearanceSettings />, { wrapper: Wrapper });
    await userEvent.click(screen.getByRole("switch", { name: "Show the color strip on Home" }));
    expect(localStorage.getItem(HOME_COLOR_STRIP_KEY)).toBe("off");
    expect(screen.getByRole("switch", { name: "Show the color strip on Home" })).not.toBeChecked();
    expect(bodies).toEqual([]);
  });
});

describe("Home colour strip", () => {
  it("draws the six board colours by default", () => {
    render(<HomeColorStrip />);
    const strip = screen.getByTestId("home-color-strip");
    expect(strip).toHaveAttribute("aria-hidden", "true");
    expect(strip.children).toHaveLength(6);
  });

  it("is gone when this browser turned it off", () => {
    localStorage.setItem(HOME_COLOR_STRIP_KEY, "off");
    render(<HomeColorStrip />);
    expect(screen.queryByTestId("home-color-strip")).not.toBeInTheDocument();
  });

  it("follows the Appearance switch live, and another tab's change", async () => {
    withDisplay({});
    render(
      <Wrapper>
        <AppearanceSettings />
        <HomeColorStrip />
      </Wrapper>,
    );
    expect(screen.getByTestId("home-color-strip")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("switch", { name: "Show the color strip on Home" }));
    expect(screen.queryByTestId("home-color-strip")).not.toBeInTheDocument();

    localStorage.setItem(HOME_COLOR_STRIP_KEY, "on");
    act(() => {
      window.dispatchEvent(new StorageEvent("storage", { key: HOME_COLOR_STRIP_KEY }));
    });
    expect(screen.getByTestId("home-color-strip")).toBeInTheDocument();
  });
});

describe("Appearance › Motion details", () => {
  it("keeps desktop-only board animation as a switch", async () => {
    const bodies = withDisplay({ board_animations: "on" });
    render(<AnimationSettings />, { wrapper: Wrapper });
    const desktop = await screen.findByRole("switch", { name: "Only on wider screens" });
    await userEvent.click(desktop);
    await waitFor(() => expect(bodies).toEqual([{ board_animations: "desktop" }]));
  });

  it("disables desktop-only while tile flips are off", async () => {
    withDisplay({ board_animations: "off" });
    render(<AnimationSettings />, { wrapper: Wrapper });
    await waitFor(() => expect(screen.getByRole("switch", { name: "Only on wider screens" })).toBeDisabled());
  });

  it("keeps site animations as a switch", async () => {
    const bodies = withDisplay({ site_animations: "on" });
    render(<AnimationSettings />, { wrapper: Wrapper });
    const site = await screen.findByRole("switch", { name: "Animate the rest of the app" });
    await waitFor(() => expect(site).toBeChecked());
    await userEvent.click(site);
    await waitFor(() => expect(bodies).toEqual([{ site_animations: "off" }]));
  });

  it("keeps the hub-wide Reduce motion switch", async () => {
    const bodies = withDisplay({ reduce_motion: false });
    render(<AnimationSettings />, { wrapper: Wrapper });
    const reduce = await screen.findByRole("switch", { name: "Reduce motion for everyone" });
    await userEvent.click(reduce);
    await waitFor(() => expect(bodies).toEqual([{ reduce_motion: true }]));
  });
});
