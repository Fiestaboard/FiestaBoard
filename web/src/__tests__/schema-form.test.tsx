import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { type JSONSchema, SchemaForm } from "@/components/plugin-settings";
import type * as apiModule from "@/lib/api";

import { server } from "./mocks/server";

/**
 * Regression tests for the bug reported in
 * "Remove Live Input Validation Logic" (FiestaBoard issue):
 *
 * When a numeric setting (e.g. Airport Latitude) had a `default` in its JSON
 * schema, the user could not delete the value: as soon as the input became
 * empty (or transiently invalid like "-" while editing a negative number),
 * the form re-rendered with the schema default and the user's edit was undone.
 * This made it impossible to clear/replace the default by typing or pasting.
 *
 * The fix has two parts:
 *  1. SchemaForm no longer substitutes `property.default` for the displayed
 *     value on every render.
 *  2. NumberField keeps a local text buffer and only commits / validates on
 *     blur, so transient editing states (empty, "-", "1.") don't get parsed
 *     into NaN/undefined and round-trip back as the previous value.
 */
/**
 * Regression tests for GitHub issues #739:
 *
 * The ArrayField component used `t("removeItem")` without calling
 * `useTranslations` — `t` was undefined, so clicking "Add" to add a first
 * item caused a ReferenceError (t is not a function) when the remove button
 * tried to render.  This manifested as the settings dialog appearing to freeze
 * with no new ticker input appearing.
 *
 * Secondary issue: ArrayField used array index as React key.  When items are
 * removed, React reuses the wrong component instances, which can cause Radix
 * UI portal cleanup to call removeChild on a detached node.
 */
describe("SchemaForm - array fields (issue #739)", () => {
  const symbolsSchema: JSONSchema = {
    type: "object",
    properties: {
      symbols: {
        type: "array",
        title: "Stock Symbols",
        description: "Symbols to track",
        maxItems: 5,
        items: { type: "string" },
        "ui:widget": "stock-symbol-picker",
      },
    },
  };

  function ArrayHarness({ initial }: { initial: Record<string, unknown> }) {
    const [values, setValues] = useState<Record<string, unknown>>(initial);
    return <SchemaForm schema={symbolsSchema} values={values} onChange={setValues} />;
  }

  it("renders add button without crashing when symbols list is empty", () => {
    const { getByRole } = render(<ArrayHarness initial={{ symbols: [] }} />);
    expect(getByRole("button", { name: /add stock symbols/i })).toBeInTheDocument();
  });

  it("adds a new item when the add button is clicked (no crash on first add)", async () => {
    const user = userEvent.setup();
    const { getByRole, getAllByRole } = render(<ArrayHarness initial={{ symbols: [] }} />);

    await user.click(getByRole("button", { name: /add stock symbols/i }));

    // A text input for the new symbol should appear
    const inputs = getAllByRole("textbox");
    expect(inputs.length).toBeGreaterThanOrEqual(1);
  });

  it("removes the correct item and leaves the right values", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    function ControlledHarness() {
      const [values, setValues] = useState<Record<string, unknown>>({
        symbols: ["AAPL", "MSFT", "GOOGL"],
      });
      return (
        <SchemaForm
          schema={symbolsSchema}
          values={values}
          onChange={(next) => {
            setValues(next);
            onChange(next);
          }}
        />
      );
    }

    render(<ControlledHarness />);

    // Remove the middle item (MSFT)
    const removeButtons = screen.getAllByRole("button", { name: "Remove item" });
    expect(removeButtons).toHaveLength(3);
    await user.click(removeButtons[1]);

    const last = onChange.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(last?.symbols).toEqual(["AAPL", "GOOGL"]);
  });

  it("renders remove buttons for pre-populated items without crashing", () => {
    const { getAllByRole } = render(<ArrayHarness initial={{ symbols: ["AAPL", "MSFT"] }} />);
    expect(getAllByRole("button", { name: "Remove item" })).toHaveLength(2);
  });
});

describe("SchemaForm - editing fields with schema defaults", () => {
  function Harness({ schema, initial }: { schema: JSONSchema; initial: Record<string, unknown> }) {
    const [values, setValues] = useState<Record<string, unknown>>(initial);
    return <SchemaForm schema={schema} values={values} onChange={setValues} />;
  }

  const numberSchema: JSONSchema = {
    type: "object",
    properties: {
      latitude: {
        type: "number",
        title: "Airport Latitude",
        default: 37.6213,
      },
    },
  };

  it("allows the user to clear a numeric field that has a schema default", async () => {
    const user = userEvent.setup();
    render(<Harness schema={numberSchema} initial={{ latitude: 37.6213 }} />);

    const input = screen.getByLabelText("Airport Latitude") as HTMLInputElement;
    expect(input.value).toBe("37.6213");

    await user.click(input);
    await user.keyboard("{Control>}a{/Control}{Backspace}");

    // Previously the field snapped back to the schema default (37.6213).
    expect(input.value).toBe("");
  });

  it("allows the user to replace a numeric default by typing a new value", async () => {
    const user = userEvent.setup();
    render(<Harness schema={numberSchema} initial={{ latitude: 37.6213 }} />);

    const input = screen.getByLabelText("Airport Latitude") as HTMLInputElement;

    await user.click(input);
    await user.keyboard("{Control>}a{/Control}{Backspace}");
    await user.type(input, "40.7128");
    await user.tab();

    expect(input.value).toBe("40.7128");
  });

  it(
    "does not snap back to the previous value while the user is mid-edit " +
      "in a negative number (e.g. deleting the digits of '-1')",
    async () => {
      const user = userEvent.setup();
      const negativeSchema: JSONSchema = {
        type: "object",
        properties: {
          latitude: {
            type: "number",
            title: "Airport Latitude",
            default: -1,
          },
        },
      };
      render(<Harness schema={negativeSchema} initial={{ latitude: -1 }} />);

      const input = screen.getByLabelText("Airport Latitude") as HTMLInputElement;
      expect(input.value).toBe("-1");

      // Delete the trailing digit; the field is now in an intermediate state
      // that is not yet a valid number. Previously this would snap back to -1.
      await user.click(input);
      await user.keyboard("{End}{Backspace}");

      expect(input.value).not.toBe("-1");

      // Finish typing a new value; the input should accept it cleanly.
      await user.type(input, "2");
      await user.tab();
      expect(input.value).toBe("-2");
    },
  );

  it("treats an entirely-cleared numeric field as undefined on blur " + "(commit-on-blur)", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    function ControlledHarness() {
      const [values, setValues] = useState<Record<string, unknown>>({ latitude: 37.6213 });
      return (
        <SchemaForm
          schema={numberSchema}
          values={values}
          onChange={(next) => {
            setValues(next);
            onChange(next);
          }}
        />
      );
    }
    render(<ControlledHarness />);

    const input = screen.getByLabelText("Airport Latitude") as HTMLInputElement;
    await user.click(input);
    await user.keyboard("{Control>}a{/Control}{Backspace}");
    await user.tab();

    const lastCall = onChange.mock.calls.at(-1)?.[0] as Record<string, unknown> | undefined;
    expect(lastCall).toBeDefined();
    expect(lastCall!.latitude).toBeUndefined();
  });

  const stringSchema: JSONSchema = {
    type: "object",
    properties: {
      city: {
        type: "string",
        title: "City",
        default: "San Francisco",
      },
    },
  };

  it("allows the user to clear a string field that has a schema default", async () => {
    const user = userEvent.setup();
    render(<Harness schema={stringSchema} initial={{ city: "San Francisco" }} />);

    const input = screen.getByLabelText("City") as HTMLInputElement;
    expect(input.value).toBe("San Francisco");

    await user.click(input);
    await user.keyboard("{Control>}a{/Control}{Backspace}");

    expect(input.value).toBe("");
  });
});

/**
 * page-picker widget: a plugin can declare `"ui:widget": "page-picker"` on a
 * string field to get a button that opens the existing PagePickerDialog and
 * writes back the chosen page UUID, instead of a raw text input.
 */
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof apiModule>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      getPages: vi.fn().mockResolvedValue({
        pages: [
          { id: "page-uuid-1", name: "Welcome", type: "template" },
          { id: "page-uuid-2", name: "Stocks", type: "template" },
        ],
        total: 2,
      }),
    },
  };
});

function QueryHarness({ children }: { children: React.ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

describe("SchemaForm - page-picker widget", () => {
  const pageSchema: JSONSchema = {
    type: "object",
    properties: {
      trigger_page_id: {
        type: "string",
        title: "Trigger Page",
        "ui:widget": "page-picker",
      },
    },
  };

  function Harness({ initial }: { initial: Record<string, unknown> }) {
    const [values, setValues] = useState<Record<string, unknown>>(initial);
    return (
      <QueryHarness>
        <SchemaForm schema={pageSchema} values={values} onChange={setValues} />
      </QueryHarness>
    );
  }

  it("renders a Select trigger (not a raw text input) for ui:widget: page-picker", async () => {
    render(<Harness initial={{ trigger_page_id: "" }} />);

    // The picker is a Radix Select trigger, exposing role=combobox.
    expect(await screen.findByRole("combobox")).toBeInTheDocument();
    // The raw text input fallback must NOT be rendered.
    expect(screen.queryByRole("textbox", { name: /trigger page/i })).not.toBeInTheDocument();
    // With no value, the dropdown's trigger surfaces the "None (no override)"
    // option, which maps to "" in the form state.
    expect(await screen.findByText(/none \(no override\)/i)).toBeInTheDocument();
  });

  it("shows the selected page's name once the pages have loaded", async () => {
    render(<Harness initial={{ trigger_page_id: "page-uuid-2" }} />);

    expect(await screen.findByText("Stocks")).toBeInTheDocument();
  });
});

describe("SchemaForm - numeric enum (integer Select)", () => {
  const enumSchema: JSONSchema = {
    type: "object",
    properties: {
      minutes_before: {
        type: "integer",
        title: "Lead Time",
        default: 5,
        enum: [1, 2, 3, 5, 10],
      },
    },
  };

  function Harness({
    initial,
    onChange,
  }: {
    initial: Record<string, unknown>;
    onChange?: (v: Record<string, unknown>) => void;
  }) {
    const [values, setValues] = useState<Record<string, unknown>>(initial);
    return (
      <SchemaForm
        schema={enumSchema}
        values={values}
        onChange={(v) => {
          setValues(v);
          onChange?.(v);
        }}
      />
    );
  }

  it("renders as a Select trigger (combobox), not a number input", () => {
    render(<Harness initial={{ minutes_before: 5 }} />);

    // The combobox role identifies a Radix Select trigger.
    expect(screen.getByRole("combobox")).toBeInTheDocument();
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it("uses enumNames as friendly labels when provided", () => {
    const labeledSchema: JSONSchema = {
      type: "object",
      properties: {
        stay_minutes: {
          type: "integer",
          title: "Stay On Board",
          default: 0,
          enum: [0, 5, 15],
          enumNames: ["Until next page", "5 min", "15 min"],
        },
      },
    };
    function Local() {
      const [values, setValues] = useState<Record<string, unknown>>({ stay_minutes: 0 });
      return <SchemaForm schema={labeledSchema} values={values} onChange={setValues} />;
    }
    render(<Local />);

    // The Select trigger displays the friendly label for the current value.
    expect(screen.getByText("Until next page")).toBeInTheDocument();
  });
});

/**
 * Declarative array-of-objects: a plugin can describe a repeatable picker
 * entirely in its manifest — an array whose `items` is an object with an
 * enum-typed property — and get a Select per entry with no core-side,
 * plugin-specific widget. Option labels come from the manifest's `enumNames`.
 */
describe("SchemaForm - declarative array of objects with an enum property", () => {
  const stationsSchema = (overrides?: { maxItems?: number }): JSONSchema => ({
    type: "object",
    properties: {
      stations: {
        type: "array",
        title: "Stations",
        description: "Select the stations you want to monitor.",
        ...(overrides?.maxItems !== undefined ? { maxItems: overrides.maxItems } : {}),
        items: {
          type: "object",
          properties: {
            station_id: {
              type: "integer",
              title: "Station",
              enum: [1, 7, 9],
              enumNames: ["North Terminal", "South Terminal", "East Terminal"],
            },
          },
          required: ["station_id"],
        },
      },
    },
  });

  function Harness({
    schema,
    initial,
    onChange,
  }: {
    schema: JSONSchema;
    initial: Record<string, unknown>;
    onChange?: (v: Record<string, unknown>) => void;
  }) {
    const [values, setValues] = useState<Record<string, unknown>>(initial);
    return (
      <SchemaForm
        schema={schema}
        values={values}
        onChange={(v) => {
          setValues(v);
          onChange?.(v);
        }}
      />
    );
  }

  it("renders one Select per stored entry, labelled from the manifest's enumNames", () => {
    render(<Harness schema={stationsSchema()} initial={{ stations: [{ station_id: 7 }, { station_id: 9 }] }} />);

    const selects = screen.getAllByRole("combobox");
    expect(selects).toHaveLength(2);
    expect(screen.getByText("South Terminal")).toBeInTheDocument();
    expect(screen.getByText("East Terminal")).toBeInTheDocument();
    // No raw number inputs — the enum must win over the free-number field.
    expect(screen.queryByRole("spinbutton")).not.toBeInTheDocument();
  });

  it("round-trips an already-stored value without rewriting it on render", () => {
    const onChange = vi.fn();
    render(<Harness schema={stationsSchema()} initial={{ stations: [{ station_id: 1 }] }} onChange={onChange} />);

    // The stored id maps to its manifest label…
    expect(screen.getByText("North Terminal")).toBeInTheDocument();
    // …and merely rendering must not mutate the persisted config.
    expect(onChange).not.toHaveBeenCalled();
  });

  it("keeps the stored object shape when a different option is selected", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness schema={stationsSchema()} initial={{ stations: [{ station_id: 1 }] }} onChange={onChange} />);

    await user.click(screen.getByRole("combobox"));
    await user.click(await screen.findByRole("option", { name: "East Terminal" }));

    const last = onChange.mock.calls.at(-1)?.[0] as { stations: unknown[] };
    expect(last.stations).toEqual([{ station_id: 9 }]);
  });

  it("falls back to the first enum value when a newly added entry's property declares no default", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness schema={stationsSchema()} initial={{ stations: [] }} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: /add stations/i }));

    // The Select already *displays* the first option, so persisting `{}` here
    // would silently save a config that doesn't match what the user sees — and
    // would drop the property the plugin lists as required.
    const last = onChange.mock.calls.at(-1)?.[0] as { stations: unknown[] };
    expect(last.stations).toEqual([{ station_id: 1 }]);
  });

  it("seeds a newly added entry with the property's default when it differs from the first enum value", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    // A manifest is free to declare a `default` that isn't `enum[0]` — several
    // shipped plugins already do. The Select renders `default` in preference to
    // `enum[0]`, so seeding `enum[0]` here would persist something other than
    // what the user sees and make the declared default unreachable.
    const schema: JSONSchema = {
      type: "object",
      properties: {
        pets: {
          type: "array",
          title: "Pets",
          items: {
            type: "object",
            properties: {
              animal: { type: "string", title: "Animal", enum: ["cat", "dog", "random"], default: "random" },
            },
          },
        },
      },
    };
    render(<Harness schema={schema} initial={{ pets: [] }} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: /add pets/i }));

    const last = onChange.mock.calls.at(-1)?.[0] as { pets: unknown[] };
    expect(last.pets).toEqual([{ animal: "random" }]);
  });

  it("honours a falsy default such as 0 rather than falling back to the first enum value", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    // `0` is a legitimate default and the Select does display it. Picking the
    // seed must therefore be a presence check, not a truthiness check, or the
    // seed silently drifts back to `enum[0]` for every falsy default.
    const schema: JSONSchema = {
      type: "object",
      properties: {
        offsets: {
          type: "array",
          title: "Offsets",
          items: {
            type: "object",
            properties: {
              minutes: { type: "integer", title: "Minutes", enum: [1, 0, 5], default: 0 },
            },
          },
        },
      },
    };
    render(<Harness schema={schema} initial={{ offsets: [] }} onChange={onChange} />);

    await user.click(screen.getByRole("button", { name: /add offsets/i }));

    const last = onChange.mock.calls.at(-1)?.[0] as { offsets: unknown[] };
    expect(last.offsets).toEqual([{ minutes: 0 }]);
    // The persisted seed matches what the Select shows for the fresh entry.
    expect(screen.getByRole("combobox")).toHaveTextContent("0");
  });

  it("removes the entry the user clicked remove on", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <Harness
        schema={stationsSchema()}
        initial={{ stations: [{ station_id: 1 }, { station_id: 7 }, { station_id: 9 }] }}
        onChange={onChange}
      />,
    );

    const removeButtons = screen.getAllByRole("button", { name: "Remove item" });
    expect(removeButtons).toHaveLength(3);
    await user.click(removeButtons[1]);

    const last = onChange.mock.calls.at(-1)?.[0] as { stations: unknown[] };
    expect(last.stations).toEqual([{ station_id: 1 }, { station_id: 9 }]);
  });

  it("hides the add button once maxItems entries are present", () => {
    const { unmount } = render(
      <Harness schema={stationsSchema({ maxItems: 2 })} initial={{ stations: [{ station_id: 1 }] }} />,
    );
    expect(screen.getByRole("button", { name: /add stations/i })).toBeInTheDocument();
    unmount();

    render(
      <Harness
        schema={stationsSchema({ maxItems: 2 })}
        initial={{ stations: [{ station_id: 1 }, { station_id: 7 }] }}
      />,
    );
    expect(screen.queryByRole("button", { name: /add stations/i })).not.toBeInTheDocument();
  });
});

/**
 * A parks-and-rides picker built entirely out of generic primitives: an array
 * of objects whose `park_id` and `ride_ids` are both `remote-options` fields,
 * exactly as the Disney plugin's manifest declares them from v1.3.0 on.
 *
 * These assertions were written against the bespoke `disney-parks-times-picker`
 * widget core used to ship, and are kept — repointed at the generic primitive —
 * because what they protect is user-facing behaviour, not an implementation:
 * per-choice display names and reorder arrows stay opt-in (`labels_field` and
 * `reorderable` replacing the old `customRideNames` / `reorderRides` flags), the
 * remove control is always there, and reordering rewrites the persisted order.
 *
 * The composition is the point. `RemoteOptionsField`'s own suite covers each
 * capability on a flat schema; here they are nested one level down, inside an
 * array row, where the label map has to land on the row's own `custom_names`
 * and the picker has to resolve `depends_on: ["park_id"]` against its sibling.
 */
const PARK_OPTIONS = [{ value: 5, label: "Magic Kingdom" }];
const RIDE_OPTIONS = [
  { value: 1, label: "Space Mountain" },
  { value: 2, label: "Haunted Mansion" },
];

/** Serve both catalogs the manifest names, chosen by `options_id`. */
function mockParkAndRideOptions() {
  server.use(
    http.post("/api/plugins/:pluginId/options/:optionsId", ({ params }) => {
      const optionsId = String(params.optionsId);
      const options = optionsId === "parks" ? PARK_OPTIONS : RIDE_OPTIONS;
      return HttpResponse.json({
        plugin_id: String(params.pluginId),
        options_id: optionsId,
        options,
        has_more: false,
        cursor: null,
        total: options.length,
        error: null,
        cached: false,
        stale: false,
        cache_seconds: 300,
      });
    }),
  );
}

describe("SchemaForm - parks and rides via the generic remote-options widget", () => {
  const parkSchema = (rideUiOptions: Record<string, unknown> = {}): JSONSchema => ({
    type: "object",
    properties: {
      parks: {
        type: "array",
        title: "Parks and rides",
        items: {
          type: "object",
          properties: {
            park_id: {
              type: "integer",
              title: "Park",
              "ui:widget": "remote-options",
              "ui:options": { options_id: "parks" },
            },
            ride_ids: {
              type: "array",
              title: "Rides",
              items: { type: "integer" },
              "ui:widget": "remote-options",
              "ui:options": { options_id: "rides", depends_on: ["park_id"], multiple: true, ...rideUiOptions },
            },
            custom_names: { type: "object", title: "Custom ride names" },
          },
          required: ["park_id", "ride_ids"],
        },
      },
    },
  });

  function Harness({
    schema,
    initial,
    onChange,
  }: {
    schema: JSONSchema;
    initial: Record<string, unknown>;
    onChange?: (v: Record<string, unknown>) => void;
  }) {
    const [values, setValues] = useState<Record<string, unknown>>(initial);
    return (
      <QueryHarness>
        <SchemaForm
          schema={schema}
          values={values}
          pluginId="disney-parks-times"
          onChange={(v) => {
            setValues(v);
            onChange?.(v);
          }}
        />
      </QueryHarness>
    );
  }

  const oneParkTwoRides = { parks: [{ park_id: 5, ride_ids: [1, 2], custom_names: {} }] };

  it("hides reorder arrows and the display-name input when the manifest asks for neither", async () => {
    mockParkAndRideOptions();
    render(<Harness schema={parkSchema()} initial={oneParkTwoRides} />);

    // Ride names render once the catalog has loaded.
    expect(await screen.findByText("Space Mountain")).toBeInTheDocument();
    // The remove button is always available.
    expect(screen.getByRole("button", { name: "Remove Space Mountain" })).toBeInTheDocument();
    // Gated controls must NOT be present.
    expect(screen.queryByRole("button", { name: "Move Space Mountain up" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Move Space Mountain down" })).not.toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: /display name for space mountain/i })).not.toBeInTheDocument();
  });

  it("shows reorder arrows only when reorderable is set, and reorders on click", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    mockParkAndRideOptions();
    render(<Harness schema={parkSchema({ reorderable: true })} initial={oneParkTwoRides} onChange={onChange} />);

    expect(await screen.findByText("Space Mountain")).toBeInTheDocument();
    // First ride can't move up (disabled) but can move down.
    expect(screen.getByRole("button", { name: "Move Space Mountain up" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Move Space Mountain down" }));

    const last = onChange.mock.calls.at(-1)?.[0] as { parks: { ride_ids: number[] }[] };
    expect(last.parks[0].ride_ids).toEqual([2, 1]);
  });

  it("shows the display-name input only when labels_field is set", async () => {
    mockParkAndRideOptions();
    render(<Harness schema={parkSchema({ labels_field: "custom_names" })} initial={oneParkTwoRides} />);

    expect(await screen.findByText("Space Mountain")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Display name for Space Mountain" })).toBeInTheDocument();
    // Reorder remains gated independently.
    expect(screen.queryByRole("button", { name: "Move Space Mountain up" })).not.toBeInTheDocument();
  });

  it("writes and clears the row's custom_names as the user edits the label", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    mockParkAndRideOptions();
    render(
      <Harness schema={parkSchema({ labels_field: "custom_names" })} initial={oneParkTwoRides} onChange={onChange} />,
    );

    const input = (await screen.findByRole("textbox", {
      name: "Display name for Space Mountain",
    })) as HTMLInputElement;

    await user.type(input, "Rocket");
    let last = onChange.mock.calls.at(-1)?.[0] as { parks: { custom_names?: Record<string, string> }[] };
    expect(last.parks[0].custom_names).toEqual({ "1": "Rocket" });

    await user.clear(input);
    last = onChange.mock.calls.at(-1)?.[0] as { parks: { custom_names?: Record<string, string> }[] };
    expect(last.parks[0].custom_names).toEqual({});
  });
});
