/**
 * The wizard's welcome message goes to the display the wizard set up: a
 * board an output-plugin or TV step created is named, so a seeded
 * placeholder Vestaboard left as the primary is never the one greeted.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { BoardConfig } from "@/components/wizard/step-board-setup";
import { StepWelcome } from "@/components/wizard/step-welcome";

import { server } from "./mocks/server";

const BOARD_CONFIG: BoardConfig = {
  output_config: { api_mode: "cloud" },
  connectionVerified: true,
  device_type: "flagship",
  board_color: "black",
  code62_glyph: "degree",
};

const PLUGINS = { date_time: { enabled: false, timezone: "UTC" }, registry_selected: [] };

let bodies: unknown[] = [];

beforeEach(() => {
  bodies = [];
  server.use(
    http.post("/api/send-welcome-message", async ({ request }) => {
      const text = await request.text();
      bodies.push(text ? JSON.parse(text) : null);
      return HttpResponse.json({ message: "Welcome message sent to your board!", sent: true });
    }),
  );
});

function renderStep(props: Partial<Parameters<typeof StepWelcome>[0]>) {
  render(
    <StepWelcome
      boardConfig={BOARD_CONFIG}
      pluginConfig={PLUGINS}
      onComplete={() => {}}
      isLoading={false}
      setIsLoading={() => {}}
      {...props}
    />,
  );
}

describe("the wizard's welcome message", () => {
  it("finishes on Home without sending a welcome message", async () => {
    const complete = vi.fn();
    renderStep({ onComplete: complete });
    await userEvent.click(screen.getByRole("button", { name: /Finish setup/i }));
    await waitFor(() => expect(complete).toHaveBeenCalledWith("/"));
    expect(bodies).toEqual([]);
  });

  it("keeps an installed integration when enabling fails and lets the user finish later", async () => {
    const complete = vi.fn();
    let installs = 0;
    server.use(
      http.get("/api/plugins", () => HttpResponse.json({ plugins: [{ id: "weather" }], total: 1 })),
      http.post("/api/plugins/registry/weather/install", () => {
        installs++;
        return HttpResponse.json({});
      }),
      http.patch("/api/v1/plugins/weather", () => HttpResponse.json({ detail: "Set your location" }, { status: 400 })),
    );
    renderStep({ pluginConfig: { ...PLUGINS, registry_selected: ["weather"] }, onComplete: complete });
    await userEvent.click(screen.getByRole("button", { name: /Finish setup/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Set your location");
    expect(complete).not.toHaveBeenCalled();
    expect(installs).toBe(0);
    await userEvent.click(screen.getByRole("button", { name: /configure integrations later/i }));
    expect(complete).toHaveBeenCalledWith("/");
  });

  it("saves selected integrations before finishing without sending a message", async () => {
    const saved: unknown[] = [];
    const complete = vi.fn();
    server.use(
      http.patch("/api/v1/plugins/date_time", async ({ request }) => {
        saved.push(await request.json());
        return HttpResponse.json({});
      }),
    );
    renderStep({
      pluginConfig: { date_time: { enabled: true, timezone: "Europe/Paris" }, registry_selected: [] },
      onComplete: complete,
    });
    await userEvent.click(screen.getByRole("button", { name: /Finish setup/i }));
    await waitFor(() => expect(complete).toHaveBeenCalled());
    expect(saved).toContainEqual({ config: { timezone: "Europe/Paris" } });
    expect(saved).toContainEqual({ enabled: true });
    expect(bodies).toEqual([]);
  });

  it("shows failed integrations and retries without repeating successful saves", async () => {
    let attempts = 0;
    const complete = vi.fn();
    const dateWrites: unknown[] = [];
    server.use(
      http.get("/api/plugins", () => HttpResponse.json({ plugins: [{ id: "countdown" }], total: 1 })),
      http.patch("/api/v1/plugins/date_time", async ({ request }) => {
        dateWrites.push(await request.json());
        return HttpResponse.json({});
      }),
      http.patch("/api/v1/plugins/countdown", () => {
        attempts++;
        return attempts === 1
          ? HttpResponse.json({ detail: "Choose an event date first" }, { status: 400 })
          : HttpResponse.json({});
      }),
    );
    renderStep({
      pluginConfig: { date_time: { enabled: true, timezone: "UTC" }, registry_selected: ["countdown"] },
      onComplete: complete,
    });
    await userEvent.click(screen.getByRole("button", { name: /Finish setup/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose an event date first");
    expect(complete).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /Finish setup/i }));
    await waitFor(() => expect(complete).toHaveBeenCalled());
    expect(attempts).toBe(2);
    expect(dateWrites).toHaveLength(2);
  });

  it("enables built-in Countdown without trying to install it", async () => {
    const complete = vi.fn();
    let installs = 0;
    let enables = 0;
    server.use(
      http.get("/api/plugins", () => HttpResponse.json({ plugins: [], total: 0 })),
      http.post("/api/plugins/registry/countdown/install", () => {
        installs++;
        return HttpResponse.json({});
      }),
      http.patch("/api/v1/plugins/countdown", () => {
        enables++;
        return HttpResponse.json({});
      }),
    );
    renderStep({ pluginConfig: { ...PLUGINS, registry_selected: ["countdown"] }, onComplete: complete });
    await userEvent.click(screen.getByRole("button", { name: /Finish setup/i }));
    await waitFor(() => expect(complete).toHaveBeenCalled());
    expect(enables).toBe(1);
    expect(installs).toBe(0);
  });

  it("does not finish while a request is in progress", () => {
    renderStep({ isLoading: true });
    expect(screen.getByRole("button", { name: "Finish setup" })).toBeDisabled();
  });
});
