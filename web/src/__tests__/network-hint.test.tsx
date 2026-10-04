/**
 * The network hint: a scan carries the private IPv4 address the page was
 * opened at as `hint_host`, for every output, so an output in Docker bridge
 * mode searches the user's network instead of the container's. Never for
 * localhost, a hostname, a public address, or an action that is not a scan.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PluginBoardSettings } from "@/components/settings/plugin-board-settings";
import type { ActionResult, OutputActionDescriptor, OutputSummary } from "@/lib/api";
import { lanHintHost } from "@/lib/network-hint";

import { server } from "./mocks/server";

const page = vi.hoisted(() => ({ hostname: "localhost" }));
vi.mock("@/lib/network-hint", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/network-hint")>();
  return { ...actual, browserHostname: () => page.hostname };
});

afterEach(() => {
  page.hostname = "localhost";
});

const API = "/api";

function action(overrides: Partial<OutputActionDescriptor> & { id: string }): OutputActionDescriptor {
  return { label: overrides.id, description: "", builtin: false, input_schema: null, result_fields: {}, ...overrides };
}

function output(actions: OutputActionDescriptor[], pickerAction = "discover"): OutputSummary {
  return {
    id: "acme_sign",
    name: "Acme Sign",
    description: "",
    icon: "monitor",
    builtin: false,
    beta_gated: false,
    available: true,
    output_api: 1,
    capabilities: {
      technology: "led_matrix",
      delivery: "push",
      animation: "stream",
      native_transitions: [],
      charset: null,
    },
    device_models: [{ id: "divoom_pixoo64", label: "Divoom Pixoo 64" }],
    settings_schema: {
      type: "object",
      properties: {
        host: {
          type: "string",
          title: "Sign address",
          "ui:widget": "device-picker",
          "ui:options": { action: pickerAction },
        },
      },
    },
    actions,
  };
}

const DISCOVER = action({ id: "discover", label: "Find signs", builtin: true });
const TEST = action({ id: "test_connection", label: "Test connection", builtin: true });
const FIND = action({
  id: "find_sign",
  label: "Find my sign",
  input_schema: {
    type: "object",
    properties: {
      subnet: { type: "string", title: "Network to search" },
      hint_host: { type: "string", title: "Address you opened FiestaBoard at" },
    },
  },
});

function result(overrides: Partial<ActionResult> = {}): ActionResult {
  return { status: "ok", message: "", guidance: [], fields: null, geometry: null, devices: [], ...overrides };
}

function Harness({ summary }: { summary: OutputSummary }) {
  const [values, setValues] = useState<Record<string, unknown>>({});
  return <PluginBoardSettings output={summary} values={values} onChange={setValues} deviceModel="divoom_pixoo64" />;
}

function renderScreen(summary: OutputSummary) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <Harness summary={summary} />
    </QueryClientProvider>,
  );
}

/** Records the body of every request to the draft action route. */
function recordBodies(): Record<string, Record<string, unknown>> {
  const bodies: Record<string, Record<string, unknown>> = {};
  server.use(
    http.post(`${API}/outputs/acme_sign/actions/:action`, async ({ request, params }) => {
      bodies[String(params.action)] = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(result());
    }),
  );
  return bodies;
}

describe("lanHintHost", () => {
  it.each(["192.168.1.20", "10.0.0.5", "172.16.4.2", "172.31.255.1", "169.254.10.1"])("keeps %s", (host) => {
    expect(lanHintHost(host)).toBe(host);
  });

  it.each([
    "localhost",
    "127.0.0.1",
    "fiestaboard.local",
    "fiestaboard",
    "8.8.8.8",
    "203.0.113.5",
    "172.32.0.1",
    "192.168.1.256",
    "[::1]",
    "",
  ])("drops %s", (host) => {
    expect(lanHintHost(host)).toBeNull();
  });
});

describe("the device picker's scan", () => {
  it("sends the page's private IPv4 address as hint_host", async () => {
    page.hostname = "192.168.1.20";
    const bodies = recordBodies();
    renderScreen(output([DISCOVER, TEST]));
    await userEvent.click(screen.getByRole("button", { name: "Find signs" }));
    await waitFor(() => expect(bodies.discover).toBeDefined());
    expect(bodies.discover.input).toEqual({ hint_host: "192.168.1.20" });
  });

  it.each(["localhost", "fiestaboard.local", "203.0.113.5"])("sends no hint when the page is at %s", async (host) => {
    page.hostname = host;
    const bodies = recordBodies();
    renderScreen(output([DISCOVER, TEST]));
    await userEvent.click(screen.getByRole("button", { name: "Find signs" }));
    await waitFor(() => expect(bodies.discover).toBeDefined());
    expect(bodies.discover).not.toHaveProperty("input");
  });

  it("sends the hint to a picker's own action, and offers a subnet field when it declares one", async () => {
    page.hostname = "10.0.0.8";
    const bodies = recordBodies();
    renderScreen(output([FIND, TEST], "find_sign"));
    await userEvent.type(screen.getByLabelText("Network to search"), "10.0.4.0/24");
    await userEvent.click(screen.getByRole("button", { name: "Find my sign" }));
    await waitFor(() => expect(bodies.find_sign).toBeDefined());
    expect(bodies.find_sign.input).toEqual({ subnet: "10.0.4.0/24", hint_host: "10.0.0.8" });
  });

  it("offers no subnet field when the action declares none", () => {
    renderScreen(output([DISCOVER, TEST]));
    expect(screen.queryByLabelText(/network to search/i)).not.toBeInTheDocument();
  });
});

describe("action buttons", () => {
  it("fills hint_host into a scan action's input instead of asking for it", async () => {
    page.hostname = "192.168.0.12";
    const bodies = recordBodies();
    const summary = output([FIND, TEST]);
    renderScreen({ ...summary, settings_schema: { type: "object", properties: {} } });
    await userEvent.click(screen.getByRole("button", { name: "Find my sign" }));
    const dialog = await screen.findByRole("dialog");
    expect(screen.queryByLabelText("Address you opened FiestaBoard at")).not.toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Network to search"), "192.168.0.0/24");
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByTestId("action-result");
    expect(dialog).not.toBeInTheDocument();
    expect(bodies.find_sign.input).toEqual({ subnet: "192.168.0.0/24", hint_host: "192.168.0.12" });
  });

  it("never sends the hint with an action that is not a scan", async () => {
    page.hostname = "192.168.0.12";
    const bodies = recordBodies();
    renderScreen(output([DISCOVER, TEST]));
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    await screen.findByTestId("action-result");
    expect(bodies.test_connection).not.toHaveProperty("input");
  });
});
