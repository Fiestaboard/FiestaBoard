/**
 * The device picker and action feedback, as a person setting up a Pixoo
 * meets them: a search says what it is doing while it runs, what it found
 * shows right under the address field as a pick-list (one result picked for
 * you), nothing found says so with a way forward (type the address, the
 * output's other lookup, search again), and every action answers next to
 * the button that ran it — never in one box at the bottom of the form. A
 * required setting still empty says so on the field itself.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PluginBoardSettings } from "@/components/settings/plugin-board-settings";
import type { ActionResult, DiscoveredDevice, OutputSummary } from "@/lib/api";

import { server } from "./mocks/server";

const page = vi.hoisted(() => ({ hostname: "192.168.0.12" }));
vi.mock("@/lib/network-hint", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/network-hint")>();
  return { ...actual, browserHostname: () => page.hostname };
});

afterEach(() => {
  page.hostname = "192.168.0.12";
});

const API = "/api";

/** Shaped like the Divoom Pixoo output's manifest. */
const PIXOO: OutputSummary = {
  id: "divoom_pixoo",
  name: "Divoom Pixoo",
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
        title: "Device address",
        description: "Use Find my Pixoo, or type it in.",
        "ui:widget": "device-picker",
        "ui:options": { action: "find_pixoo", value_key: "host", label_key: "label" },
      },
      mac: { type: "string", title: "Device MAC address" },
    },
    required: ["host"],
  },
  actions: [
    {
      id: "find_pixoo",
      label: "Find my Pixoo",
      description: "",
      builtin: false,
      input_schema: {
        type: "object",
        properties: { subnet: { type: "string", title: "Network to search" }, hint_host: { type: "string" } },
      },
      result_fields: {},
    },
    {
      id: "cloud_lookup",
      label: "Ask Divoom's servers",
      description: "",
      builtin: false,
      input_schema: null,
      result_fields: { host: { secret: false, fills: "host" }, mac: { secret: false, fills: "mac" } },
    },
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

function result(overrides: Partial<ActionResult> = {}): ActionResult {
  return { status: "ok", message: "", guidance: [], fields: null, geometry: null, devices: null, ...overrides };
}

function pixoo(ip: string, mac = "a1b2c3d4e5f6"): DiscoveredDevice {
  return { ip, port: 80, hostname: null, source: null, label: `Pixoo 64 at ${ip}`, fields: { host: ip, mac } };
}

function answer(action: string, body: ActionResult | (() => Promise<ActionResult>)) {
  server.use(
    http.post(`${API}/outputs/divoom_pixoo/actions/${action}`, async () =>
      HttpResponse.json(typeof body === "function" ? await body() : body),
    ),
  );
}

function Harness({ initial = {} }: { initial?: Record<string, unknown> }) {
  const [values, setValues] = useState<Record<string, unknown>>(initial);
  return (
    <>
      <PluginBoardSettings output={PIXOO} values={values} onChange={setValues} deviceModel="divoom_pixoo64" />
      <output data-testid="values">{JSON.stringify(values)}</output>
    </>
  );
}

function renderScreen(initial?: Record<string, unknown>) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Harness initial={initial} />
    </QueryClientProvider>,
  );
}

function values(): Record<string, unknown> {
  return JSON.parse(screen.getByTestId("values").textContent ?? "{}");
}

const picker = () => screen.getByTestId("device-picker");
const address = () => within(picker()).getByRole("textbox", { name: /^Device address/ });

describe("searching", () => {
  it("says which network it is searching while the search runs", async () => {
    let finish: (r: ActionResult) => void = () => {};
    answer("find_pixoo", () => new Promise((resolve) => (finish = resolve)));
    renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "Find my Pixoo" }));

    const status = await within(picker()).findByTestId("device-picker-status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveTextContent("Searching 192.168.0.x…");
    expect(within(picker()).getByRole("button", { name: /Find my Pixoo/ })).toHaveAttribute("aria-busy", "true");

    finish(result({ devices: [] }));
    await waitFor(() => expect(status).not.toHaveTextContent("Searching"));
  });

  it("names the network the user typed instead of the page's", async () => {
    answer("find_pixoo", () => new Promise(() => {}));
    renderScreen();
    await userEvent.type(screen.getByLabelText("Network to search"), "10.0.4.0/24");
    await userEvent.click(screen.getByRole("button", { name: "Find my Pixoo" }));
    expect(await within(picker()).findByText("Searching 10.0.4.0/24…")).toBeInTheDocument();
  });
});

describe("what a search found", () => {
  it("picks the only device found and fills its address, right under the field", async () => {
    answer("find_pixoo", result({ message: "Found 1 Pixoo(s) on 192.168.0.0/24.", devices: [pixoo("192.168.0.224")] }));
    renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "Find my Pixoo" }));

    const list = await within(picker()).findByRole("radiogroup", { name: /Devices found/ });
    expect(within(list).getByRole("radio", { name: /Pixoo 64 at 192\.168\.0\.224/ })).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await waitFor(() => expect(values()).toEqual({ host: "192.168.0.224", mac: "a1b2c3d4e5f6" }));
    expect(address()).toHaveValue("192.168.0.224");
    expect(within(picker()).getByTestId("device-picker-status")).toHaveTextContent(
      "Found 1 Pixoo(s) on 192.168.0.0/24.",
    );
  });

  it("lets the user choose among several, picking none for them", async () => {
    answer("find_pixoo", result({ devices: [pixoo("192.168.0.224"), pixoo("192.168.0.225", "0011223344ff")] }));
    renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "Find my Pixoo" }));

    const list = await within(picker()).findByRole("radiogroup", { name: /Devices found/ });
    expect(within(list).getAllByRole("radio")).toHaveLength(2);
    expect(within(list).queryByRole("radio", { checked: true })).not.toBeInTheDocument();
    expect(values()).toEqual({});
    expect(within(picker()).getByTestId("device-picker-status")).toHaveTextContent("Found 2 devices. Choose yours.");

    await userEvent.click(within(list).getByRole("radio", { name: /192\.168\.0\.225/ }));
    await waitFor(() => expect(values()).toEqual({ host: "192.168.0.225", mac: "0011223344ff" }));
  });

  it("says nothing was found on which network, and offers the address, the other lookup and another search", async () => {
    answer("find_pixoo", result({ status: "warning", message: "No Pixoo found on 192.168.0.0/24.", devices: [] }));
    let lookups = 0;
    server.use(
      http.post(`${API}/outputs/divoom_pixoo/actions/cloud_lookup`, () => {
        lookups += 1;
        return HttpResponse.json(
          result({
            message: "Divoom knows one Pixoo on your network.",
            fields: { host: { value: "192.168.0.230", secret: false, fills: "host" } },
          }),
        );
      }),
    );
    renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "Find my Pixoo" }));

    const empty = await within(picker()).findByTestId("device-picker-empty");
    expect(empty).toHaveTextContent("No Pixoo found on 192.168.0.0/24.");

    await userEvent.click(within(empty).getByRole("button", { name: "Enter address manually" }));
    expect(address()).toHaveFocus();

    await userEvent.click(within(empty).getByRole("button", { name: "Ask Divoom's servers" }));
    expect(await within(empty).findByText("Divoom knows one Pixoo on your network.")).toBeInTheDocument();
    expect(lookups).toBe(1);
    await waitFor(() => expect(values().host).toBe("192.168.0.230"));

    expect(within(empty).getByRole("button", { name: "Search again" })).toBeInTheDocument();
  });

  it("falls back to the output's name and the page's network when the search says nothing", async () => {
    answer("find_pixoo", result({ devices: [] }));
    renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "Find my Pixoo" }));
    expect(await within(picker()).findByTestId("device-picker-empty")).toHaveTextContent(
      "No Divoom Pixoo found on 192.168.0.x.",
    );
  });

  it("searches again from the result", async () => {
    let searches = 0;
    server.use(
      http.post(`${API}/outputs/divoom_pixoo/actions/find_pixoo`, () => {
        searches += 1;
        return HttpResponse.json(result({ devices: [] }));
      }),
    );
    renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "Find my Pixoo" }));
    await userEvent.click(await within(picker()).findByRole("button", { name: "Search again" }));
    await waitFor(() => expect(searches).toBe(2));
  });

  it("shows a search that could not run under the field, with another try", async () => {
    server.use(
      http.post(`${API}/outputs/divoom_pixoo/actions/find_pixoo`, () =>
        HttpResponse.json({ detail: "The scan was refused." }, { status: 400 }),
      ),
    );
    renderScreen();
    await userEvent.click(screen.getByRole("button", { name: "Find my Pixoo" }));
    const failure = await within(picker()).findByTestId("action-failure");
    expect(failure).toHaveTextContent("The scan was refused.");
    expect(within(picker()).getByRole("button", { name: "Search again" })).toBeInTheDocument();
  });
});

describe("typing the address", () => {
  it("offers manual entry before any search, and it focuses the address field", async () => {
    renderScreen();
    await userEvent.click(within(picker()).getByRole("button", { name: "Enter address manually" }));
    expect(address()).toHaveFocus();
  });
});

describe("action feedback", () => {
  it("answers next to the button that ran the action", async () => {
    answer(
      "test_connection",
      result({ status: "error", message: "No answer from 192.0.2.5.", guidance: ["Check it is on."] }),
    );
    renderScreen({ host: "192.0.2.5" });
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));

    const item = screen.getByTestId("action-item-test_connection");
    const panel = await within(item).findByTestId("action-result");
    expect(panel).toHaveAttribute("data-status", "error");
    expect(panel).toHaveTextContent("No answer from 192.0.2.5.");
    expect(panel).toHaveTextContent("Check it is on.");
    expect(within(item).getByTestId("action-feedback-test_connection")).toHaveAttribute("aria-live", "polite");
  });

  it("shows a request that failed next to its button too", async () => {
    server.use(
      http.post(`${API}/outputs/divoom_pixoo/actions/test_connection`, () =>
        HttpResponse.json({ detail: "Server error" }, { status: 500 }),
      ),
    );
    renderScreen({ host: "192.0.2.5" });
    await userEvent.click(screen.getByRole("button", { name: "Test connection" }));
    const item = screen.getByTestId("action-item-test_connection");
    expect(await within(item).findByTestId("action-failure")).toBeInTheDocument();
  });

  it("keeps the picker's other lookup out of the action row", () => {
    renderScreen();
    expect(screen.queryByTestId("action-item-cloud_lookup")).not.toBeInTheDocument();
  });
});

describe("required settings", () => {
  it("says on the field itself that it is needed, not in a list at the bottom", async () => {
    renderScreen();
    const field = address();
    expect(field).toHaveAccessibleDescription(/Required/);
    expect(screen.queryByText(/Still needed/)).not.toBeInTheDocument();

    await userEvent.type(field, "192.0.2.5");
    expect(field).not.toHaveAccessibleDescription(/Required/);
  });
});
