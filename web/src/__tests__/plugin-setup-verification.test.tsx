import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { StepOutputPlugin, type WizardCreatedBoard } from "@/components/wizard/step-output-plugin";
import type { OutputSummary } from "@/lib/api";

import { server } from "./mocks/server";

const output: OutputSummary = {
  id: "my_sign",
  name: "My Sign",
  description: "Example",
  icon: null,
  builtin: false,
  available: true,
  beta_gated: false,
  output_api: 1,
  capabilities: {
    technology: "led_matrix",
    delivery: "push",
    animation: "none",
    native_transitions: [],
    charset: null,
  },
  device_models: [{ id: "small_sign", label: "Small" }],
  settings_schema: { type: "object", properties: { host: { type: "string", title: "Address" } } },
  actions: [
    {
      id: "test_connection",
      label: "Test connection",
      description: "",
      builtin: true,
      input_schema: null,
      result_fields: {},
    },
  ],
};
function Harness() {
  const [created, setCreated] = useState<WizardCreatedBoard | null>(null);
  return (
    <StepOutputPlugin
      output={output}
      created={created}
      onCreated={setCreated}
      onValidChange={() => {}}
      setIsLoading={() => {}}
      replacePlaceholder={false}
    />
  );
}
function setup(testable = true, overrides: Partial<OutputSummary> = {}) {
  server.use(
    http.post("/api/outputs/my_sign/install", () =>
      HttpResponse.json({ ...output, actions: testable ? output.actions : [], ...overrides }),
    ),
    http.post("/api/outputs/my_sign/actions/test_connection", () =>
      HttpResponse.json({
        status: "ok",
        message: "Connected",
        guidance: [],
        fields: null,
        devices: null,
        geometry: null,
      }),
    ),
    http.post("/api/outputs/my_sign/boards", () => HttpResponse.json({ id: "board-1", name: "My Sign" })),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: 1, retryDelay: 0 } } })
      }
    >
      <Harness />
    </QueryClientProvider>,
  );
}

describe("plugin connection verification", () => {
  it("does not automatically repeat a board creation after a failed response", async () => {
    setup(false);
    let writes = 0;
    server.use(
      http.post("/api/outputs/my_sign/boards", () => {
        writes += 1;
        return HttpResponse.json(
          { detail: "The response was interrupted. Check Displays before trying again." },
          { status: 503 },
        );
      }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Add board" }));
    await screen.findByTestId("wizard-output-create-error");
    expect(writes).toBe(1);
  });
  it("saves a plugin without test support without claiming a verified connection", async () => {
    setup(false);
    expect(await screen.findByText(/does not provide a connection test/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Add board" }));
    expect(await screen.findByTestId("wizard-output-created")).toHaveTextContent("Connection has not been verified");
  });
  it("invalidates verification after editing and after a failed retest", async () => {
    setup();
    const input = await screen.findByLabelText("Address");
    await userEvent.type(input, "192.0.2.1");
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    expect(await screen.findByTestId("plugin-connection-status")).toHaveTextContent("Connection verified");
    await userEvent.type(input, "0");
    expect(screen.getByTestId("plugin-connection-status")).toHaveTextContent("Connection not verified");
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    await waitFor(() =>
      expect(screen.getByTestId("plugin-connection-status")).toHaveTextContent("Connection verified"),
    );
    server.use(
      http.post("/api/outputs/my_sign/actions/test_connection", () =>
        HttpResponse.json({ detail: "Device unreachable" }, { status: 503 }),
      ),
    );
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    await screen.findByText("Device unreachable");
    expect(screen.getByTestId("plugin-connection-status")).toHaveTextContent("Connection not verified");
  });
  it("carries verification through save when the tested configuration is unchanged", async () => {
    setup();
    await userEvent.click(await screen.findByRole("button", { name: "Test connection" }));
    await waitFor(() =>
      expect(screen.getByTestId("plugin-connection-status")).toHaveTextContent("Connection verified"),
    );
    await userEvent.click(screen.getByRole("button", { name: "Add board" }));
    expect(await screen.findByTestId("wizard-output-created")).toHaveTextContent("Connection verified");
  });
});

describe("plugin-owned setup requirements", () => {
  it("renders settings and actions conditional on the chosen model and draft type", async () => {
    setup(true, {
      settings_schema: {
        type: "object",
        properties: {
          host: {
            type: "string",
            title: "Model address",
            "ui:visible_when": { "@device_model": "small_sign", "@device_type": "panel" },
          },
        },
      },
    });
    expect(await screen.findByLabelText("Model address")).toBeInTheDocument();
  });
  it.each([
    [{ kind: "panel" }, "Rows", "Columns", { rows: 8, cols: 32 }],
    [{ kind: "note_array" }, "Notes tall", "Notes wide", { notes_tall: 8, notes_wide: 2 }],
  ])("submits configurable geometry for %j", async (geometry, rowLabel, colLabel, expected) => {
    const bodies: unknown[] = [];
    setup(false, { device_models: [{ id: "custom", label: "Custom display", geometry }] });
    server.use(
      http.post("/api/outputs/my_sign/boards", async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ id: "custom-board", name: "My Sign" });
      }),
    );
    const rows = await screen.findByLabelText(rowLabel);
    const cols = screen.getByLabelText(colLabel);
    await userEvent.clear(rows);
    await userEvent.type(rows, "8");
    await userEvent.clear(cols);
    await userEvent.type(cols, colLabel === "Notes wide" ? "2" : "32");
    await userEvent.click(screen.getByRole("button", { name: "Add board" }));
    await screen.findByTestId("wizard-output-created");
    expect(bodies).toEqual([{ name: "My Sign", device_model: "custom", output_config: {}, geometry: expected }]);
  });
  it("applies detected dimensions and clears them when switching to a fixed model", async () => {
    setup(false, {
      device_models: [
        { id: "custom", label: "Custom display", geometry: { kind: "panel" } },
        { id: "fixed", label: "Fixed display", geometry: { kind: "cells", rows: 6, cols: 22 } },
      ],
      actions: [
        {
          id: "detect_geometry",
          label: "Detect size",
          description: "",
          builtin: true,
          input_schema: null,
          result_fields: {},
          auto_apply: true,
        },
      ],
    });
    server.use(
      http.post("/api/outputs/my_sign/actions/detect_geometry", () =>
        HttpResponse.json({
          status: "ok",
          message: "Size found",
          guidance: [],
          fields: null,
          devices: null,
          geometry: {
            device_type: "panel",
            rows: 8,
            cols: 32,
            notes_wide: null,
            notes_tall: null,
            matched_preset: null,
          },
        }),
      ),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Detect size" }));
    await waitFor(() => expect(screen.getByLabelText("Rows")).toHaveValue(8));
    expect(screen.getByLabelText("Columns")).toHaveValue(32);
    await userEvent.click(screen.getByRole("combobox"));
    await userEvent.click(await screen.findByRole("option", { name: "Fixed display" }));
    expect(screen.queryByLabelText("Rows")).not.toBeInTheDocument();
    const bodies: unknown[] = [];
    server.use(
      http.post("/api/outputs/my_sign/boards", async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ id: "fixed-board", name: "My Sign" });
      }),
    );
    await userEvent.click(screen.getByRole("button", { name: "Add board" }));
    await screen.findByTestId("wizard-output-created");
    expect(bodies).toEqual([{ name: "My Sign", device_model: "fixed", output_config: {} }]);
  });
});
