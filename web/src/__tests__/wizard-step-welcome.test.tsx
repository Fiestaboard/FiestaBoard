/**
 * The wizard's welcome message goes to the display the wizard set up: a
 * board an output-plugin or TV step created is named, so a seeded
 * placeholder Vestaboard left as the primary is never the one greeted.
 */
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

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
