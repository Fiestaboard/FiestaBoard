import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";

import { type JSONSchema, SchemaForm } from "@/components/plugin-settings";
import type * as apiModule from "@/lib/api";

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
