import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { delay, http, HttpResponse } from "msw";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { type JSONSchema, SchemaForm } from "@/components/plugin-settings";

import { server } from "./mocks/server";

/**
 * The generic `remote-options` settings widget.
 *
 * Plugins declare `"ui:widget": "remote-options"` plus a `ui:options` block in
 * their manifest; core renders one widget for all of them and asks the backend
 * (`POST /plugins/{plugin_id}/options/{options_id}`) for the catalog. Nothing
 * here is plugin-specific — that is the whole point of the primitive.
 */

const OPTIONS_PATH = "/api/plugins/:pluginId/options/:optionsId";

interface CapturedRequest {
  pluginId: string;
  optionsId: string;
  body: {
    parent?: Record<string, unknown>;
    query?: string;
  };
}

interface MockOption {
  value: string | number | boolean;
  label: string;
  description?: string | null;
  group?: string | null;
  preview?: string | null;
  disabled?: boolean;
  meta?: Record<string, unknown> | null;
}

/**
 * Install an MSW handler for the options route and return the array it records
 * every request into, so a test can assert both *what* was asked for and — for
 * the `depends_on` gate — that nothing was asked at all.
 */
function mockOptions(options: MockOption[], overrides: Record<string, unknown> = {}): CapturedRequest[] {
  const captured: CapturedRequest[] = [];
  server.use(
    http.post(OPTIONS_PATH, async ({ params, request }) => {
      captured.push({
        pluginId: String(params.pluginId),
        optionsId: String(params.optionsId),
        body: (await request.json()) as CapturedRequest["body"],
      });
      return HttpResponse.json({
        plugin_id: String(params.pluginId),
        options_id: String(params.optionsId),
        options,
        has_more: false,
        cursor: null,
        total: options.length,
        error: null,
        cached: false,
        stale: false,
        cache_seconds: 300,
        ...overrides,
      });
    }),
  );
  return captured;
}

function Harness({
  schema,
  initial,
  pluginId = "disney-parks-times",
  onChange,
}: {
  schema: JSONSchema;
  initial: Record<string, unknown>;
  pluginId?: string;
  onChange?: (values: Record<string, unknown>) => void;
}) {
  const [values, setValues] = useState<Record<string, unknown>>(initial);
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
  return (
    <QueryClientProvider client={client}>
      <SchemaForm
        schema={schema}
        values={values}
        pluginId={pluginId}
        onChange={(next) => {
          setValues(next);
          onChange?.(next);
        }}
      />
    </QueryClientProvider>
  );
}

const singleSchema: JSONSchema = {
  type: "object",
  properties: {
    park_id: {
      type: "integer",
      title: "Park",
      "ui:widget": "remote-options",
      "ui:options": { options_id: "parks" },
    },
  },
};

describe("RemoteOptionsField - single select", () => {
  it("renders the stored value's catalog label instead of a raw input", async () => {
    mockOptions([
      { value: 16, label: "Magic Kingdom" },
      { value: 5, label: "Epcot" },
    ]);

    render(<Harness schema={singleSchema} initial={{ park_id: 16 }} />);

    expect(await screen.findByText("Magic Kingdom")).toBeInTheDocument();
    // The bare number input the field would otherwise fall back to must be gone.
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it("stores the option's declared JSON type — an integer stays an integer", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    mockOptions([
      { value: 16, label: "Magic Kingdom" },
      { value: 5, label: "Epcot" },
    ]);

    render(<Harness schema={singleSchema} initial={{ park_id: 16 }} onChange={onChange} />);

    await user.click(await screen.findByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: "Epcot" }));

    const last = onChange.mock.calls.at(-1)?.[0] as { park_id: unknown };
    expect(last.park_id).toBe(5);
    expect(last.park_id).not.toBe("5");
  });
});

const dependentSchema: JSONSchema = {
  type: "object",
  properties: {
    agency: {
      type: "string",
      title: "Transit Agency",
      enum: ["SF", "AC"],
      enumNames: ["SF Muni", "AC Transit"],
    },
    stop_code: {
      type: "string",
      title: "Stop",
      "ui:widget": "remote-options",
      "ui:options": { options_id: "stops", depends_on: ["agency"] },
    },
  },
};

describe("RemoteOptionsField - depends_on", () => {
  it("stays disabled and issues no request while the parent field is unset", async () => {
    const captured = mockOptions([{ value: "13915", label: "Market St & 5th" }]);

    render(<Harness schema={dependentSchema} initial={{ agency: "", stop_code: "" }} pluginId="muni" />);

    expect(await screen.findByText("Select Transit Agency first")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Stop" })).toBeDisabled();
    // The whole point of the gate: an unscoped catalog request is never useful,
    // so it must not be sent at all.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(captured).toHaveLength(0);
  });

  it("sends the resolved parent values so the plugin can scope the catalog", async () => {
    const captured = mockOptions([{ value: "13915", label: "Market St & 5th" }]);

    render(<Harness schema={dependentSchema} initial={{ agency: "SF", stop_code: "13915" }} pluginId="muni" />);

    expect(await screen.findByText("Market St & 5th")).toBeInTheDocument();
    expect(captured).toHaveLength(1);
    expect(captured[0].pluginId).toBe("muni");
    expect(captured[0].optionsId).toBe("stops");
    expect(captured[0].body.parent).toEqual({ agency: "SF" });
  });

  it("refetches for the new parent and drops the now-stale child value", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const captured: CapturedRequest[] = [];
    server.use(
      http.post(OPTIONS_PATH, async ({ params, request }) => {
        const body = (await request.json()) as CapturedRequest["body"];
        captured.push({ pluginId: String(params.pluginId), optionsId: String(params.optionsId), body });
        const agency = body.parent?.agency;
        return HttpResponse.json({
          plugin_id: String(params.pluginId),
          options_id: String(params.optionsId),
          options:
            agency === "SF"
              ? [{ value: "13915", label: "Market St & 5th" }]
              : [{ value: "55555", label: "Broadway & 12th" }],
          has_more: false,
          cursor: null,
          total: 1,
          error: null,
          cached: false,
          stale: false,
          cache_seconds: 300,
        });
      }),
    );

    render(
      <Harness
        schema={dependentSchema}
        initial={{ agency: "SF", stop_code: "13915" }}
        pluginId="muni"
        onChange={onChange}
      />,
    );
    expect(await screen.findByText("Market St & 5th")).toBeInTheDocument();

    await user.click(screen.getByRole("combobox", { name: "Transit Agency" }));
    await user.click(await screen.findByRole("option", { name: "AC Transit" }));

    // The catalog is re-asked for, scoped to the new parent…
    await waitFor(() => expect(captured).toHaveLength(2));
    expect(captured[1].body.parent).toEqual({ agency: "AC" });
    // …and the stop code from the previous agency, which cannot exist in the
    // new one, is dropped rather than silently persisted.
    await waitFor(() => {
      const last = onChange.mock.calls.at(-1)?.[0] as { stop_code: unknown };
      expect(last.stop_code).toBeUndefined();
    });
  });
});

/**
 * `depends_on` names a *sibling*. In an array of objects the sibling lives in
 * the array item, and in a nested object it lives in that sub-object — not at
 * the root. Resolving against the root instead silently scopes the catalog by
 * the wrong value (or by nothing), so both shapes are covered.
 */
const stopField = {
  type: "string" as const,
  title: "Stop",
  "ui:widget": "remote-options",
  "ui:options": { options_id: "stops", depends_on: ["agency"] },
};

const agencyField = {
  type: "string" as const,
  title: "Transit Agency",
  enum: ["SF", "AC"],
  enumNames: ["SF Muni", "AC Transit"],
};

describe("RemoteOptionsField - depends_on scope resolution", () => {
  it("resolves depends_on against the array item, not the root config", async () => {
    const captured = mockOptions([{ value: "13915", label: "Market St & 5th" }]);
    const schema: JSONSchema = {
      type: "object",
      properties: {
        routes: {
          type: "array",
          title: "Routes",
          items: { type: "object", properties: { agency: agencyField, stop_code: stopField } },
        },
      },
    };

    render(
      <Harness
        schema={schema}
        // The root deliberately disagrees with the item: if the widget reads
        // the root, it asks for AC Transit stops for a Muni route.
        initial={{ agency: "AC", routes: [{ agency: "SF", stop_code: "13915" }] }}
        pluginId="muni"
      />,
    );

    expect(await screen.findByText("Market St & 5th")).toBeInTheDocument();
    expect(captured[0].body.parent).toEqual({ agency: "SF" });
  });

  it("resolves depends_on against the nested object, not the root config", async () => {
    const captured = mockOptions([{ value: "13915", label: "Market St & 5th" }]);
    const schema: JSONSchema = {
      type: "object",
      properties: {
        route: {
          type: "object",
          title: "Route",
          properties: { agency: agencyField, stop_code: stopField },
        },
      },
    };

    render(
      <Harness
        schema={schema}
        initial={{ agency: "AC", route: { agency: "SF", stop_code: "13915" } }}
        pluginId="muni"
      />,
    );

    expect(await screen.findByText("Market St & 5th")).toBeInTheDocument();
    expect(captured[0].body.parent).toEqual({ agency: "SF" });
  });
});

describe("RemoteOptionsField - response states", () => {
  it("renders inline destructive text and a Retry button when the request fails", async () => {
    const user = userEvent.setup();
    let attempts = 0;
    server.use(
      http.post(OPTIONS_PATH, async ({ params }) => {
        attempts += 1;
        if (attempts === 1) {
          return HttpResponse.json({ detail: "upstream exploded" }, { status: 502 });
        }
        return HttpResponse.json({
          plugin_id: String(params.pluginId),
          options_id: String(params.optionsId),
          options: [{ value: 16, label: "Magic Kingdom" }],
          has_more: false,
          cursor: null,
          total: 1,
          error: null,
          cached: false,
          stale: false,
          cache_seconds: 300,
        });
      }),
    );

    render(<Harness schema={singleSchema} initial={{ park_id: 16 }} />);

    expect(await screen.findByText("Could not load options")).toBeInTheDocument();
    // A transport failure is an incident the user can act on, so it gets a
    // retry affordance rather than only a message.
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Magic Kingdom")).toBeInTheDocument();
    expect(attempts).toBe(2);
  });

  it("shows data.error as a quiet inline hint, not an incident", async () => {
    mockOptions([], { error: "Add an API key first" });

    render(<Harness schema={singleSchema} initial={{ park_id: "" }} />);

    expect(await screen.findByText("Add an API key first")).toBeInTheDocument();
    // "Not configured yet" is not a failure: no destructive framing, no retry,
    // and — since it is inline — no toast.
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    expect(screen.queryByText("Could not load options")).not.toBeInTheDocument();
  });

  it("says so when the catalog comes back empty", async () => {
    mockOptions([]);

    render(<Harness schema={singleSchema} initial={{ park_id: "" }} />);

    expect(await screen.findByText("No options available")).toBeInTheDocument();
  });

  it("notes when the backend served a stale cache", async () => {
    mockOptions([{ value: 16, label: "Magic Kingdom" }], { stale: true, cached: true });

    render(<Harness schema={singleSchema} initial={{ park_id: 16 }} />);

    expect(await screen.findByText("Showing cached results")).toBeInTheDocument();
  });

  it("invites the user to narrow the search when a server-searched catalog is truncated", async () => {
    const searchableSchema: JSONSchema = {
      type: "object",
      properties: {
        park_id: {
          type: "integer",
          title: "Park",
          "ui:widget": "remote-options",
          "ui:options": { options_id: "parks", server_search: true },
        },
      },
    };
    mockOptions([{ value: 16, label: "Magic Kingdom" }], { has_more: true, total: 62 });

    render(<Harness schema={searchableSchema} initial={{ park_id: 16 }} />);

    expect(await screen.findByText("Refine your search to see more")).toBeInTheDocument();
  });

  it("keeps a stored value the catalog no longer offers, rendered as itself", async () => {
    const onChange = vi.fn();
    mockOptions([
      { value: 16, label: "Magic Kingdom" },
      { value: 5, label: "Epcot" },
    ]);

    render(<Harness schema={singleSchema} initial={{ park_id: 999 }} onChange={onChange} />);

    // Assert only once the catalog has actually arrived — while it is in
    // flight every value looks unrecognised, which would pass vacuously.
    await waitFor(() => expect(screen.queryByText("Loading options…")).not.toBeInTheDocument());
    // Blanking the field, or quietly snapping it to another option, would
    // rewrite the user's config behind their back on the next save.
    expect(screen.getByText("999")).toBeInTheDocument();
    expect(screen.queryByText("Magic Kingdom")).not.toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });
});

const TICKERS: MockOption[] = [
  { value: "AAPL", label: "Apple Inc." },
  { value: "MSFT", label: "Microsoft Corp." },
  { value: "GOOG", label: "Alphabet Inc." },
];

function multiSchema(uiOptions: Record<string, unknown> = {}, extra: Record<string, unknown> = {}): JSONSchema {
  return {
    type: "object",
    properties: {
      symbols: {
        type: "array",
        title: "Symbols",
        items: { type: "string" },
        "ui:widget": "remote-options",
        "ui:options": { options_id: "symbols", multiple: true, ...uiOptions },
        ...extra,
      },
    },
  };
}

describe("RemoteOptionsField - multi select", () => {
  it("lists the chosen options by label, in stored order", async () => {
    mockOptions(TICKERS);

    render(<Harness schema={multiSchema()} initial={{ symbols: ["MSFT", "AAPL"] }} pluginId="stocks" />);

    await screen.findByText("Microsoft Corp.");
    const chosen = screen.getAllByTestId("remote-options-chosen");
    expect(chosen.map((node) => node.textContent)).toEqual([
      expect.stringContaining("Microsoft Corp."),
      expect.stringContaining("Apple Inc."),
    ]);
  });

  it("omits already-chosen options from the add list", async () => {
    const user = userEvent.setup();
    mockOptions(TICKERS);

    render(<Harness schema={multiSchema()} initial={{ symbols: ["AAPL"] }} pluginId="stocks" />);

    await user.click(await screen.findByRole("combobox", { name: "Add option" }));

    expect(await screen.findByRole("option", { name: "Alphabet Inc." })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Microsoft Corp." })).toBeInTheDocument();
    // Offering a chosen ticker again can only produce a duplicate.
    expect(screen.queryByRole("option", { name: "Apple Inc." })).not.toBeInTheDocument();
  });

  it("appends a newly chosen option at the end, preserving selection order", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    mockOptions(TICKERS);

    render(<Harness schema={multiSchema()} initial={{ symbols: ["MSFT"] }} pluginId="stocks" onChange={onChange} />);

    await user.click(await screen.findByRole("combobox", { name: "Add option" }));
    await user.click(await screen.findByRole("option", { name: "Apple Inc." }));

    const last = onChange.mock.calls.at(-1)?.[0] as { symbols: unknown };
    expect(last.symbols).toEqual(["MSFT", "AAPL"]);
  });

  it("removes the chosen option the remove button names", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    mockOptions(TICKERS);

    render(
      <Harness schema={multiSchema()} initial={{ symbols: ["MSFT", "AAPL"] }} pluginId="stocks" onChange={onChange} />,
    );

    await user.click(await screen.findByRole("button", { name: "Remove Microsoft Corp." }));

    const last = onChange.mock.calls.at(-1)?.[0] as { symbols: unknown };
    expect(last.symbols).toEqual(["AAPL"]);
  });

  it("disables the add list once maxItems is reached", async () => {
    mockOptions(TICKERS);

    render(
      <Harness schema={multiSchema({}, { maxItems: 2 })} initial={{ symbols: ["MSFT", "AAPL"] }} pluginId="stocks" />,
    );

    // Wait for the catalog: while it is in flight the control is disabled
    // anyway, which would make this assertion pass for the wrong reason.
    await screen.findByText("Microsoft Corp.");
    expect(screen.getByRole("combobox", { name: "Add option" })).toBeDisabled();
  });

  it("leaves the add list usable below maxItems", async () => {
    mockOptions(TICKERS);

    render(<Harness schema={multiSchema({}, { maxItems: 3 })} initial={{ symbols: ["MSFT"] }} pluginId="stocks" />);

    await screen.findByText("Microsoft Corp.");
    expect(screen.getByRole("combobox", { name: "Add option" })).toBeEnabled();
  });

  it("hides reorder arrows unless the manifest asks for them", async () => {
    mockOptions(TICKERS);

    render(<Harness schema={multiSchema()} initial={{ symbols: ["MSFT", "AAPL"] }} pluginId="stocks" />);

    await screen.findByText("Microsoft Corp.");
    expect(screen.queryByRole("button", { name: "Move Microsoft Corp. down" })).not.toBeInTheDocument();
  });

  it("moves a chosen option when reorderable and the arrow is clicked", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    mockOptions(TICKERS);

    render(
      <Harness
        schema={multiSchema({ reorderable: true })}
        initial={{ symbols: ["MSFT", "AAPL"] }}
        pluginId="stocks"
        onChange={onChange}
      />,
    );

    // The first item cannot move up, only down.
    expect(await screen.findByRole("button", { name: "Move Microsoft Corp. up" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Move Microsoft Corp. down" }));

    const last = onChange.mock.calls.at(-1)?.[0] as { symbols: unknown };
    expect(last.symbols).toEqual(["AAPL", "MSFT"]);
  });

  it("keeps a chosen value the catalog no longer offers, rendered as itself", async () => {
    const onChange = vi.fn();
    mockOptions(TICKERS);

    render(<Harness schema={multiSchema()} initial={{ symbols: ["AAPL", "DELISTED"] }} pluginId="stocks" />);

    expect(await screen.findByText("Apple Inc.")).toBeInTheDocument();
    expect(screen.getByText("DELISTED")).toBeInTheDocument();
    expect(onChange).not.toHaveBeenCalled();
  });
});

describe("RemoteOptionsField - loading", () => {
  it("disables the control and shows a spinner while the catalog is in flight", async () => {
    server.use(
      http.post(OPTIONS_PATH, async ({ params }) => {
        await delay(60);
        return HttpResponse.json({
          plugin_id: String(params.pluginId),
          options_id: String(params.optionsId),
          options: [{ value: 16, label: "Magic Kingdom" }],
          has_more: false,
          cursor: null,
          total: 1,
          error: null,
          cached: false,
          stale: false,
          cache_seconds: 300,
        });
      }),
    );

    render(<Harness schema={singleSchema} initial={{ park_id: 16 }} />);

    expect(screen.getByText("Loading options…")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeDisabled();

    expect(await screen.findByText("Magic Kingdom")).toBeInTheDocument();
    expect(screen.queryByText("Loading options…")).not.toBeInTheDocument();
  });
});

describe("RemoteOptionsField - search", () => {
  const DESCRIBED: MockOption[] = [
    { value: "AAPL", label: "Apple Inc.", description: "Consumer electronics" },
    { value: "MSFT", label: "Microsoft Corp.", description: "Cloud and software" },
  ];

  it("has no search box unless the manifest asks for one", async () => {
    mockOptions(DESCRIBED);

    render(<Harness schema={multiSchema()} initial={{ symbols: [] }} pluginId="stocks" />);

    await screen.findByRole("combobox", { name: "Add option" });
    expect(screen.queryByRole("searchbox")).not.toBeInTheDocument();
  });

  it("filters client-side over label and description when searchable, with no extra request", async () => {
    const user = userEvent.setup();
    const captured = mockOptions(DESCRIBED);

    render(<Harness schema={multiSchema({ searchable: true })} initial={{ symbols: [] }} pluginId="stocks" />);

    await screen.findByRole("combobox", { name: "Add option" });
    // "cloud" appears only in Microsoft's description, never in a label.
    await user.type(screen.getByRole("searchbox", { name: "Search options" }), "cloud");
    await user.click(screen.getByRole("combobox", { name: "Add option" }));

    expect(await screen.findByRole("option", { name: /Microsoft Corp\./ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Apple Inc\./ })).not.toBeInTheDocument();
    // Client-side means client-side: the plugin is not asked again.
    expect(captured).toHaveLength(1);
  });

  it("debounces one request per pause when server_search is set", async () => {
    const user = userEvent.setup();
    const captured = mockOptions(TICKERS);

    render(<Harness schema={multiSchema({ server_search: true })} initial={{ symbols: [] }} pluginId="stocks" />);

    await screen.findByRole("combobox", { name: "Add option" });
    expect(captured).toHaveLength(1);
    expect(captured[0].body.query).toBe("");

    await user.type(screen.getByRole("searchbox", { name: "Search options" }), "goog");

    await waitFor(() => expect(captured).toHaveLength(2), { timeout: 3000 });
    expect(captured[1].body.query).toBe("goog");
    // Four keystrokes, one round trip — the debounce is not per-character.
    await delay(400);
    expect(captured).toHaveLength(2);
  });
});

describe("RemoteOptionsField - allow_custom", () => {
  it("commits a typed value the catalog does not contain", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    mockOptions(TICKERS);

    render(
      <Harness
        schema={multiSchema({ allow_custom: true })}
        initial={{ symbols: [] }}
        pluginId="stocks"
        onChange={onChange}
      />,
    );

    const input = await screen.findByRole("textbox", { name: "Custom value" });
    await user.type(input, "BRK.B");
    await user.click(screen.getByRole("button", { name: "Add custom value" }));

    const last = onChange.mock.calls.at(-1)?.[0] as { symbols: unknown };
    expect(last.symbols).toEqual(["BRK.B"]);
  });

  it("offers no custom-value entry unless the manifest allows it", async () => {
    mockOptions(TICKERS);

    render(<Harness schema={multiSchema()} initial={{ symbols: [] }} pluginId="stocks" />);

    await screen.findByRole("combobox", { name: "Add option" });
    expect(screen.queryByRole("textbox", { name: "Custom value" })).not.toBeInTheDocument();
  });
});

describe("RemoteOptionsField - cache_seconds", () => {
  it("reuses the cached catalog across a remount instead of refetching", async () => {
    const user = userEvent.setup();
    const captured = mockOptions(TICKERS);

    function ToggleHarness() {
      const [mounted, setMounted] = useState(true);
      const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
      return (
        <QueryClientProvider client={client}>
          <button type="button" data-testid="toggle" onClick={() => setMounted((m) => !m)}>
            {"toggle"}
          </button>
          {mounted && (
            <SchemaForm
              schema={multiSchema({ cache_seconds: 300 })}
              values={{ symbols: [] }}
              onChange={() => {}}
              pluginId="stocks"
            />
          )}
        </QueryClientProvider>
      );
    }

    render(<ToggleHarness />);
    await screen.findByRole("combobox", { name: "Add option" });
    expect(captured).toHaveLength(1);

    await user.click(screen.getByTestId("toggle"));
    await user.click(screen.getByTestId("toggle"));
    await screen.findByRole("combobox", { name: "Add option" });

    // Within cache_seconds the catalog is still fresh, so remounting the
    // settings dialog must not re-hit the plugin's upstream service.
    await delay(50);
    expect(captured).toHaveLength(1);
  });
});

describe("RemoteOptionsField - placeholder", () => {
  it("uses the manifest's placeholder for the empty single select", async () => {
    mockOptions([{ value: 16, label: "Magic Kingdom" }]);
    const schema: JSONSchema = {
      type: "object",
      properties: {
        park_id: {
          type: "integer",
          title: "Park",
          "ui:widget": "remote-options",
          "ui:options": { options_id: "parks", placeholder: "Pick a park" },
        },
      },
    };

    render(<Harness schema={schema} initial={{}} />);

    expect(await screen.findByText("Pick a park")).toBeInTheDocument();
  });
});

describe("RemoteOptionsField - missing plugin context", () => {
  it("degrades to a disabled control and issues no request when SchemaForm has no pluginId", async () => {
    const captured = mockOptions([{ value: 16, label: "Magic Kingdom" }]);

    function NoPluginHarness() {
      const [values, setValues] = useState<Record<string, unknown>>({ park_id: 16 });
      const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false } } }));
      return (
        <QueryClientProvider client={client}>
          <SchemaForm schema={singleSchema} values={values} onChange={setValues} />
        </QueryClientProvider>
      );
    }

    // Rendering without a pluginId must not throw…
    expect(() => render(<NoPluginHarness />)).not.toThrow();

    expect(await screen.findByText("Options unavailable")).toBeInTheDocument();
    expect(screen.getByRole("combobox")).toBeDisabled();
    // …and must never guess at a plugin id by firing a request anyway.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(captured).toHaveLength(0);
  });
});
