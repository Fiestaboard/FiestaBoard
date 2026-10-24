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
  it("hands off to the page editor without sending the optional welcome message", async () => {
    const complete = vi.fn();
    renderStep({ onComplete: complete });
    await userEvent.click(screen.getByRole("button", { name: /create my first page/i }));
    await waitFor(() => expect(complete).toHaveBeenCalledWith("/pages/new"));
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
    await userEvent.click(screen.getByRole("button", { name: /create my first page/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Set your location");
    expect(complete).not.toHaveBeenCalled();
    expect(installs).toBe(0);
    await userEvent.click(screen.getByRole("button", { name: /configure integrations later/i }));
    expect(complete).toHaveBeenCalledWith("/integrations");
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
    await userEvent.click(screen.getByRole("button", { name: /Go to Dashboard/i }));
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
    await userEvent.click(screen.getByRole("button", { name: /Go to Dashboard/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose an event date first");
    expect(complete).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: /Go to Dashboard/i }));
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
    await userEvent.click(screen.getByRole("button", { name: /Go to Dashboard/i }));
    await waitFor(() => expect(complete).toHaveBeenCalled());
    expect(enables).toBe(1);
    expect(installs).toBe(0);
  });

  it("does not claim a quiet-hours refusal sent or queued a message", async () => {
    server.use(
      http.post("/api/send-welcome-message", () => HttpResponse.json({ detail: "Quiet hours" }, { status: 409 })),
    );
    renderStep({});
    await userEvent.click(screen.getByRole("button", { name: /Hello from FiestaBoard/ }));
    expect(await screen.findByRole("status")).toHaveTextContent(/not sent/i);
    expect(screen.queryByRole("button", { name: "Message Sent!" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Hello from FiestaBoard/ })).toBeEnabled();
  });

  it("does not finish while a request is in progress", () => {
    renderStep({ isLoading: true });
    expect(screen.getByRole("button", { name: /Go to Dashboard/i })).toBeDisabled();
  });

  it("greets the board an output-plugin step created", async () => {
    renderStep({
      output: { id: "divoom_pixoo", name: "Divoom Pixoo" },
      createdBoard: { outputId: "divoom_pixoo", boardId: "px1", name: "Desk" },
    });
    await userEvent.click(screen.getByRole("button", { name: /Hello from FiestaBoard/ }));
    await waitFor(() => expect(bodies).toEqual([{ board_id: "px1" }]));
  });

  it("greets the primary board on the Vestaboard path, as before", async () => {
    renderStep({ output: { id: "vestaboard", name: "Vestaboard" } });
    await userEvent.click(screen.getByRole("button", { name: /Hello from FiestaBoard/ }));
    await waitFor(() => expect(bodies).toEqual([null]));
  });
});
